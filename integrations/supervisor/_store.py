"""Atomic I/O for integration ``.meta`` (plaintext) and ``.enc`` (ciphertext) files.

Every write goes through ``tmp + fsync + rename`` so readers always see a
coherent file. Non-secret metadata is plaintext JSON; only the credential
bundle is encrypted. This split is what lets the ``list`` and permission-toggle
paths avoid loading the master key at all — handy because the key is the
expensive thing to touch, both for process lifecycle and for access control.

Vault layout::

    <vault_dir>/
        .master-key
        creds/
            <integration_id>.meta    plaintext JSON
            <integration_id>.enc     AES-256-GCM encrypted secret bundle
"""

from __future__ import annotations

import os
from pathlib import Path

from integrations._perms import VAULT_FILE_MODE
from integrations.supervisor._crypto import decrypt_secrets, encrypt_secrets
from integrations.supervisor.types import IntegrationMeta


def creds_dir(vault_dir: Path) -> Path:
    """Path to the per-integration creds directory."""
    return vault_dir / "creds"


def meta_path(vault_dir: Path, integration_id: str) -> Path:
    """Path to ``<id>.meta`` inside the creds dir."""
    return creds_dir(vault_dir) / f"{integration_id}.meta"


def enc_path(vault_dir: Path, integration_id: str) -> Path:
    """Path to ``<id>.enc`` inside the creds dir."""
    return creds_dir(vault_dir) / f"{integration_id}.enc"


def _atomic_write(path: Path, data: bytes, *, mode: int = VAULT_FILE_MODE) -> None:
    """Write ``data`` to ``path`` atomically, then apply ``mode``.

    Default ``mode`` is :data:`integrations._perms.VAULT_FILE_MODE`
    (``0o600``) — both ``.meta`` and ``.enc`` are owner-only.

    Writes to a ``.tmp`` sibling, fsyncs, chmods, then renames. ``rename``
    inside a single filesystem is atomic, so readers never observe a
    partially-written file — they see either the old one or the new one.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    tmp.chmod(mode)
    tmp.rename(path)


def write_meta(vault_dir: Path, meta: IntegrationMeta) -> None:
    """Atomically write the ``.meta`` file for ``meta.id``."""
    data = meta.model_dump_json().encode("utf-8")
    _atomic_write(meta_path(vault_dir, meta.id), data)


def read_meta(vault_dir: Path, integration_id: str) -> IntegrationMeta:
    """Load and validate the ``.meta`` file. Raises pydantic's ``ValidationError``
    on shape mismatch — that's deliberate, a schema-drift in .meta is a bug."""
    path = meta_path(vault_dir, integration_id)
    return IntegrationMeta.model_validate_json(path.read_text(encoding="utf-8"))


def write_secrets(
    vault_dir: Path,
    integration_id: str,
    master_key: bytes,
    secret_bundle: dict,
) -> None:
    """Encrypt ``secret_bundle`` and atomically write the ``.enc`` file."""
    blob = encrypt_secrets(master_key, integration_id, secret_bundle)
    _atomic_write(enc_path(vault_dir, integration_id), blob)


def read_secrets(
    vault_dir: Path,
    integration_id: str,
    master_key: bytes,
) -> dict:
    """Decrypt the ``.enc`` file. Raises :class:`supervisor._crypto.DecryptError`
    on any tamper or AAD mismatch."""
    blob = enc_path(vault_dir, integration_id).read_bytes()
    return decrypt_secrets(master_key, integration_id, blob)


def delete_integration(vault_dir: Path, integration_id: str) -> None:
    """Remove both ``.meta`` and ``.enc`` files for an integration.

    Idempotent — missing files are silently skipped so callers can safely call
    remove more than once without racing on partial state.
    """
    meta_path(vault_dir, integration_id).unlink(missing_ok=True)
    enc_path(vault_dir, integration_id).unlink(missing_ok=True)


def list_integration_ids(vault_dir: Path) -> list[str]:
    """Return the integration IDs that have BOTH a ``.meta`` and a ``.enc`` on disk.

    Orphans (one side missing) are silently omitted — they represent a
    partial-write crash and the pair is unusable anyway. The caller can decide
    whether to log a warning.
    """
    cdir = creds_dir(vault_dir)
    if not cdir.exists():
        return []
    meta_ids = {p.stem for p in cdir.glob("*.meta")}
    enc_ids = {p.stem for p in cdir.glob("*.enc")}
    return sorted(meta_ids & enc_ids)
