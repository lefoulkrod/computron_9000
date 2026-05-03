"""Tests for supervisor/_crypto.py — master key lifecycle + AES-GCM round-trip."""

from __future__ import annotations

from pathlib import Path

import pytest

from integrations.supervisor._crypto import (
    DecryptError,
    decrypt_secrets,
    encrypt_secrets,
    load_or_init_master_key,
)


def test_master_key_is_generated_on_first_call(tmp_path: Path) -> None:
    """First call creates the key file (0600) and returns 32 bytes."""
    key = load_or_init_master_key(tmp_path)

    assert len(key) == 32
    key_file = tmp_path / ".master-key"
    assert key_file.exists()
    assert key_file.stat().st_mode & 0o777 == 0o600


def test_master_key_is_loaded_on_subsequent_calls(tmp_path: Path) -> None:
    """Second call returns the same bytes — no key rotation or re-generation."""
    first = load_or_init_master_key(tmp_path)
    second = load_or_init_master_key(tmp_path)

    assert first == second


def test_master_key_wrong_length_raises(tmp_path: Path) -> None:
    """Corrupt key file (wrong length) is surfaced instead of silently accepted."""
    (tmp_path / ".master-key").write_bytes(b"too short")

    with pytest.raises(ValueError, match="wrong length"):
        load_or_init_master_key(tmp_path)


def test_round_trip_preserves_payload() -> None:
    """encrypt_secrets -> decrypt_secrets reproduces the original dict exactly."""
    key = load_or_init_master_key_in_memory()
    payload = {"email": "you@example.com", "password": "abcd efgh ijkl mnop"}

    blob = encrypt_secrets(key, "gmail_personal", payload)
    back = decrypt_secrets(key, "gmail_personal", blob)

    assert back == payload


def test_tampered_ciphertext_fails() -> None:
    """Flipping a byte in the ciphertext trips the GCM auth tag."""
    key = load_or_init_master_key_in_memory()
    blob = bytearray(encrypt_secrets(key, "gmail_personal", {"v": 1}))
    # Flip a byte past the 1-byte version header + 12-byte nonce — i.e. in the
    # ciphertext or auth tag region.
    blob[15] ^= 0x01

    with pytest.raises(DecryptError):
        decrypt_secrets(key, "gmail_personal", bytes(blob))


def test_wrong_aad_fails() -> None:
    """Decrypting with a different integration id fails: the AAD binding prevents
    a ``cat gmail.enc > icloud.enc`` file-swap attack."""
    key = load_or_init_master_key_in_memory()
    blob = encrypt_secrets(key, "gmail_personal", {"password": "secret"})

    with pytest.raises(DecryptError):
        decrypt_secrets(key, "icloud_personal", blob)


def test_wrong_key_fails() -> None:
    """Decrypting with a different master key fails."""
    key_a = load_or_init_master_key_in_memory()
    key_b = load_or_init_master_key_in_memory()
    blob = encrypt_secrets(key_a, "gmail_personal", {"password": "secret"})

    with pytest.raises(DecryptError):
        decrypt_secrets(key_b, "gmail_personal", blob)


def test_unknown_version_byte_fails() -> None:
    """A frame with an unrecognized version byte fails cleanly, not on auth-tag."""
    key = load_or_init_master_key_in_memory()
    blob = bytearray(encrypt_secrets(key, "x", {"v": 1}))
    blob[0] = 0xFF  # bogus version

    with pytest.raises(DecryptError, match="unknown version byte"):
        decrypt_secrets(key, "x", bytes(blob))


def test_truncated_blob_fails() -> None:
    """A blob too short to contain version + nonce + tag is rejected without
    even attempting decrypt."""
    key = load_or_init_master_key_in_memory()
    short = b"\x01" + b"\x00" * 5  # version + partial nonce, nothing else

    with pytest.raises(DecryptError, match="too short"):
        decrypt_secrets(key, "x", short)


def load_or_init_master_key_in_memory() -> bytes:
    """Convenience helper: generate a fresh key without touching the filesystem."""
    import secrets as _s

    return _s.token_bytes(32)
