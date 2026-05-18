"""Tests for the SRP-6a math in ``integrations._icloud_auth``.

The Apple endpoints themselves aren't exercised here — those need a live
network and a real Apple ID. What's testable in isolation is the SRP math:
the password-to-``x`` derivation is deterministic, and the proof exchange
should match a server-side computation built from the same parameters.
"""

from __future__ import annotations

import secrets

import pytest

from integrations._icloud_auth import (
    _G,
    _K,
    _N,
    _N_BYTES,
    _b2i,
    _h,
    _i2b,
    _srp_proofs,
    _srp_x,
)


# --- byte / int helpers ----------------------------------------------------

def test_i2b_b2i_roundtrip() -> None:
    for n in [0, 1, 255, 256, 2**128, _N - 1]:
        encoded = _i2b(n)
        assert _b2i(encoded) == n


def test_i2b_pads_to_length() -> None:
    assert _i2b(1, length=4) == b"\x00\x00\x00\x01"
    assert len(_i2b(123, length=_N_BYTES)) == _N_BYTES


def test_h_is_sha256() -> None:
    import hashlib
    assert _h(b"hello") == hashlib.sha256(b"hello").digest()
    assert _h(b"a", b"b", b"c") == hashlib.sha256(b"abc").digest()


# --- _srp_x ----------------------------------------------------------------

def test_srp_x_is_deterministic() -> None:
    salt = b"\x00" * 16
    a = _srp_x(salt, "hunter2", 20000, "s2k")
    b = _srp_x(salt, "hunter2", 20000, "s2k")
    assert a == b


def test_srp_x_in_range() -> None:
    """``x`` is a hash output, so it's a 256-bit non-negative integer."""
    x = _srp_x(b"\x01" * 16, "password", 1000, "s2k")
    assert 0 < x < 2**256


def test_srp_x_protocols_differ() -> None:
    """``s2k`` and ``s2k_fo`` MUST derive different ``x`` for the same input —
    s2k_fo pre-hashes the password before PBKDF2."""
    salt, pw, it = b"\x42" * 16, "swordfish", 5000
    assert _srp_x(salt, pw, it, "s2k") != _srp_x(salt, pw, it, "s2k_fo")


def test_srp_x_password_sensitivity() -> None:
    """A different password must yield a different ``x``."""
    salt, it = b"\x10" * 16, 10000
    assert _srp_x(salt, "alpha", it, "s2k") != _srp_x(salt, "beta", it, "s2k")


# --- SRP-6a self-consistency ----------------------------------------------


def _server_proof_round(
    username: str, password: str, salt: bytes, iteration: int, protocol: str,
    a_secret: int, big_a: int,
) -> tuple[int, int, bytes]:
    """A toy SRP-6a server implementation for self-consistency testing.

    Given the client's secret ``a`` and public ``A``, returns ``(b_secret, B, K)``
    — the server's secret, public, and derived session key. The real server
    never sees ``a`` or ``b``; we cheat here so the test can verify both sides
    landed on the same ``K`` and therefore the same proofs.
    """
    x = _srp_x(salt, password, iteration, protocol)
    v = pow(_G, x, _N)
    # Server picks random b and sends B = k*v + g^b mod N.
    b_secret = _b2i(secrets.token_bytes(32)) % _N
    big_b = (_K * v + pow(_G, b_secret, _N)) % _N
    u = _b2i(_h(_i2b(big_a, _N_BYTES), _i2b(big_b, _N_BYTES)))
    # Server-side: S = (A * v^u) ^ b mod N
    s = pow((big_a * pow(v, u, _N)) % _N, b_secret, _N)
    session_key = _h(_i2b(s, _N_BYTES))
    return b_secret, big_b, session_key


@pytest.mark.parametrize("protocol", ["s2k", "s2k_fo"])
def test_srp_full_exchange_matches_server(protocol: str) -> None:
    """Client and server should land on the same session key K.

    If they do, ``M1`` will match a server-side recomputation, which is what
    Apple checks. Iterates a few times so a one-in-a-million RNG fluke
    doesn't pass by accident.
    """
    username = "user@example.com"
    password = "correct horse battery staple"
    iteration = 2_000
    for _ in range(5):
        salt = secrets.token_bytes(16)
        # Client side: pick a, send A.
        a_secret = _b2i(secrets.token_bytes(32)) % _N
        big_a = pow(_G, a_secret, _N)
        # Server side: pick b, send B, derive K.
        _b, big_b, server_key = _server_proof_round(
            username, password, salt, iteration, protocol, a_secret, big_a,
        )
        # Client side: derive proofs.
        x = _srp_x(salt, password, iteration, protocol)
        m1, m2, client_key = _srp_proofs(a_secret, big_a, big_b, x, salt, username)
        # Same session key → same M1 derivation → server would accept the proof.
        assert client_key == server_key
        # M2 is what the server returns to prove it also derived the right K.
        # Compute server's M2 with M1 and assert it matches what the client
        # would expect to verify.
        expected_m2 = _h(_i2b(big_a, _N_BYTES), m1, server_key)
        assert m2 == expected_m2


def test_srp_proofs_lengths() -> None:
    """``M1`` and ``M2`` are SHA-256 digests — 32 bytes each."""
    salt = b"\xaa" * 16
    a = _b2i(secrets.token_bytes(32)) % _N
    big_a = pow(_G, a, _N)
    x = _srp_x(salt, "pw", 1000, "s2k")
    # Use a fake B (not derived from x) just to check shape — math validity
    # is covered by the self-consistency test above.
    big_b = pow(_G, 12345, _N)
    m1, m2, k = _srp_proofs(a, big_a, big_b, x, salt, "u@x.com")
    assert len(m1) == 32
    assert len(m2) == 32
    assert len(k) == 32


def test_srp_wrong_password_diverges() -> None:
    """If the client uses a different password, the session keys must differ."""
    username = "u@x.com"
    salt = b"\x55" * 16
    iteration = 1_000

    a_secret = _b2i(secrets.token_bytes(32)) % _N
    big_a = pow(_G, a_secret, _N)
    _b, big_b, server_key = _server_proof_round(
        username, "correct-password", salt, iteration, "s2k", a_secret, big_a,
    )
    # Client believes the password is something else.
    wrong_x = _srp_x(salt, "wrong-password", iteration, "s2k")
    _m1, _m2, client_key = _srp_proofs(a_secret, big_a, big_b, wrong_x, salt, username)
    assert client_key != server_key
