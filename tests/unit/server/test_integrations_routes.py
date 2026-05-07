"""Unit tests for helpers in ``server._integrations_routes``.

The route handlers themselves require a running supervisor on a UDS — those
go through the integration-tier suite (``tests/integrations``). The pure
helpers (``_derive_suffix``) are tested directly here.
"""

from __future__ import annotations

import pytest

from server._integrations_routes import _derive_suffix


# ── email-based derivation ────────────────────────────────────────────────────


@pytest.mark.unit
def test_derive_suffix_returns_local_part_for_simple_address() -> None:
    """A clean ASCII address → its local-part verbatim, lowercased."""
    assert _derive_suffix({"email": "alice@example.com"}) == "alice"


@pytest.mark.unit
def test_derive_suffix_lowercases_email() -> None:
    assert _derive_suffix({"email": "Alice@Example.com"}) == "alice"


@pytest.mark.unit
def test_derive_suffix_replaces_dots_and_pluses_with_dashes() -> None:
    assert _derive_suffix({"email": "alice.smith+work@x.com"}) == "alice-smith-work"


@pytest.mark.unit
def test_derive_suffix_collapses_dash_runs() -> None:
    assert _derive_suffix({"email": "a..b@x.com"}) == "a-b"


@pytest.mark.unit
def test_derive_suffix_strips_leading_and_trailing_dashes() -> None:
    assert _derive_suffix({"email": "-alice-@x.com"}) == "alice"


@pytest.mark.unit
def test_derive_suffix_preserves_underscore_and_dash() -> None:
    assert _derive_suffix({"email": "alice_smith-2@x.com"}) == "alice_smith-2"


@pytest.mark.unit
def test_derive_suffix_caps_at_48_chars() -> None:
    long_local = "a" * 100
    out = _derive_suffix({"email": f"{long_local}@x.com"})
    assert out is not None
    assert len(out) == 48
    assert out == "a" * 48


@pytest.mark.unit
def test_derive_suffix_returns_none_when_local_is_all_disallowed() -> None:
    assert _derive_suffix({"email": "++@x.com"}) is None


@pytest.mark.unit
def test_derive_suffix_handles_address_without_at_sign() -> None:
    assert _derive_suffix({"email": "noatsign"}) == "noatsign"


# ── no-suffix cases (singletons) ─────────────────────────────────────────────


@pytest.mark.unit
def test_derive_suffix_returns_none_for_non_email_blob() -> None:
    """auth_blob without email → None (caller skips suffix)."""
    assert _derive_suffix({"api_key": "sk-..."}) is None


# ── fallback / error cases ────────────────────────────────────────────────────


@pytest.mark.unit
def test_derive_suffix_returns_none_when_no_email() -> None:
    assert _derive_suffix({}) is None


@pytest.mark.unit
def test_derive_suffix_returns_none_when_email_not_a_string() -> None:
    assert _derive_suffix({"email": 123}) is None  # type: ignore[arg-type]


@pytest.mark.unit
def test_derive_suffix_returns_none_when_auth_blob_is_none() -> None:
    assert _derive_suffix(None) is None


@pytest.mark.unit
def test_derive_suffix_returns_none_when_auth_blob_is_not_a_dict() -> None:
    assert _derive_suffix("not a dict") is None  # type: ignore[arg-type]
