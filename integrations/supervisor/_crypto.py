"""AES-256-GCM encryption for credential bundles + master-key lifecycle.

The master key is 32 random bytes generated on first boot and stored plaintext
at ``<vault>/.master-key`` with Unix mode ``0600`` (rw for owner only; group
and other get nothing). The supervisor runs as its own UID so no other process
in the container can read the file; the agent in particular runs as a
different UID and the ``0600`` mode lets the kernel refuse its reads.

``encrypt_secrets`` / ``decrypt_secrets`` use AES-256-GCM with:

- A fresh 12-byte random nonce per write (never reused under the same key).
- The integration ID as AAD — the auth tag binds the ciphertext to its filename,
  so renaming ``gmail.enc`` to ``icloud.enc`` produces a decryption failure.
- A 1-byte version header (``0x01``) reserved so a future scheme can coexist
  with the current one without ambiguity.

Only the secret bundle (auth blob) is encrypted; non-secret metadata lives
plaintext in the sibling ``.meta`` file.
"""

from __future__ import annotations

import json
import secrets as _secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_KEY_BYTES = 32
_NONCE_BYTES = 12
_GCM_TAG_BYTES = 16
_VERSION = 0x01


class DecryptError(Exception):
    """Decryption failed: bad key, tampered ciphertext, wrong AAD, or version mismatch."""


def load_or_init_master_key(vault_dir: Path) -> bytes:
    """Return the supervisor's master key, generating it on first boot.

    Creates ``<vault_dir>/.master-key`` with mode ``0600`` (owner read/write
    only; group and other get no permissions) if it doesn't exist. Subsequent
    calls load the existing file. Writes atomically so a crash mid-creation
    can't leave a zero-byte file that we'd refuse to load.
    """
    path = vault_dir / ".master-key"
    if path.exists():
        data = path.read_bytes()
        if len(data) != _KEY_BYTES:
            msg = f"master key at {path} has wrong length: {len(data)}"
            raise ValueError(msg)
        return data
    key = _secrets.token_bytes(_KEY_BYTES)
    vault_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(key)
    # 0o600 = owner rw, group nothing, other nothing. Only the supervisor's UID
    # can read the master key; every other UID gets EACCES at the kernel.
    tmp.chmod(0o600)
    tmp.rename(path)
    return key


def encrypt_secrets(master_key: bytes, integration_id: str, payload: dict) -> bytes:
    """Encrypt ``payload`` under ``master_key``.

    Output framing: ``version(1) || nonce(12) || AES-256-GCM(json(payload), aad=id)``.

    The ciphertext includes the GCM auth tag (16 bytes) appended by the library.
    """
    aesgcm = AESGCM(master_key)
    nonce = _secrets.token_bytes(_NONCE_BYTES)
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    aad = integration_id.encode("utf-8")
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    return bytes([_VERSION]) + nonce + ciphertext


def decrypt_secrets(master_key: bytes, integration_id: str, blob: bytes) -> dict:
    """Reverse ``encrypt_secrets``.

    Raises :class:`DecryptError` on any failure — wrong version byte, truncated
    frame, or AEAD auth-tag mismatch (which is what fires on key/AAD/ciphertext
    tampering).
    """
    min_len = 1 + _NONCE_BYTES + _GCM_TAG_BYTES
    if len(blob) < min_len:
        msg = f"ciphertext too short: {len(blob)} < {min_len}"
        raise DecryptError(msg)
    if blob[0] != _VERSION:
        msg = f"unknown version byte: {blob[0]:#04x}"
        raise DecryptError(msg)
    nonce = blob[1 : 1 + _NONCE_BYTES]
    ciphertext = blob[1 + _NONCE_BYTES :]
    aad = integration_id.encode("utf-8")
    aesgcm = AESGCM(master_key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, aad)
    except Exception as exc:
        msg = "decryption failed (tampered ciphertext, wrong key, or wrong AAD)"
        raise DecryptError(msg) from exc
    return json.loads(plaintext.decode("utf-8"))
