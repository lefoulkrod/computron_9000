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
    """A clean ASCII address → its local-part verbatim, lowercased.

    The local-part is what disambiguates two integrations of the same provider
    (``personal@`` vs ``work@``), so it's the natural suffix source.
    """
    assert _derive_suffix({"email": "alice@example.com"}) == "alice"


@pytest.mark.unit
def test_derive_suffix_lowercases_email() -> None:
    """Mixed-case input lowercases — the supervisor's regex demands ``[a-z]``."""
    assert _derive_suffix({"email": "Alice@Example.com"}) == "alice"


@pytest.mark.unit
def test_derive_suffix_replaces_dots_and_pluses_with_dashes() -> None:
    """``.`` and ``+`` are common in email local-parts and aren't in ``[a-z0-9_-]``.
    Each non-allowed char becomes a single ``-`` after the dash-run collapse.
    """
    assert _derive_suffix({"email": "alice.smith+work@x.com"}) == "alice-smith-work"


@pytest.mark.unit
def test_derive_suffix_collapses_dash_runs() -> None:
    """Multiple disallowed chars in a row collapse to a single ``-``."""
    assert _derive_suffix({"email": "a..b@x.com"}) == "a-b"


@pytest.mark.unit
def test_derive_suffix_strips_leading_and_trailing_dashes() -> None:
    """Edges of the local-part shouldn't produce leading/trailing ``-``."""
    assert _derive_suffix({"email": "-alice-@x.com"}) == "alice"


@pytest.mark.unit
def test_derive_suffix_preserves_underscore_and_dash() -> None:
    """``_`` and ``-`` are already in the allowed set — leave them alone."""
    assert _derive_suffix({"email": "alice_smith-2@x.com"}) == "alice_smith-2"


@pytest.mark.unit
def test_derive_suffix_caps_at_48_chars() -> None:
    """Truncate to 48 chars pre-emptively rather than let the supervisor reject."""
    long_local = "a" * 100
    out = _derive_suffix({"email": f"{long_local}@x.com"})
    assert out is not None
    assert len(out) == 48
    assert out == "a" * 48


@pytest.mark.unit
def test_derive_suffix_returns_none_when_local_is_all_disallowed() -> None:
    """If sanitization eats everything, return ``None`` so the route can 400."""
    assert _derive_suffix({"email": "++@x.com"}) is None


@pytest.mark.unit
def test_derive_suffix_handles_address_without_at_sign() -> None:
    """An input without ``@`` is still sanitized as the whole string."""
    assert _derive_suffix({"email": "noatsign"}) == "noatsign"


# ── provider-based derivation (llm_proxy and future non-email slugs) ─────────


@pytest.mark.unit
def test_derive_suffix_uses_provider_when_no_email() -> None:
    """llm_proxy auth_blobs have ``provider`` but no ``email``; use it as suffix."""
    assert _derive_suffix({"provider": "openai", "api_key": "sk-..."}) == "openai"


@pytest.mark.unit
def test_derive_suffix_provider_lowercased() -> None:
    """Provider name is lowercased to satisfy the supervisor's ``[a-z0-9_-]`` regex."""
    assert _derive_suffix({"provider": "Anthropic"}) == "anthropic"


@pytest.mark.unit
def test_derive_suffix_email_takes_priority_over_provider() -> None:
    """When both ``email`` and ``provider`` are present, email wins."""
    assert _derive_suffix({"email": "bob@x.com", "provider": "openai"}) == "bob"


# ── fallback / error cases ────────────────────────────────────────────────────


@pytest.mark.unit
def test_derive_suffix_returns_none_when_both_missing() -> None:
    """No ``email`` and no ``provider`` → ``None``."""
    assert _derive_suffix({}) is None


@pytest.mark.unit
def test_derive_suffix_returns_none_when_email_not_a_string() -> None:
    """Defensive: a non-string ``email`` field shouldn't crash the route."""
    assert _derive_suffix({"email": 123}) is None  # type: ignore[arg-type]


@pytest.mark.unit
def test_derive_suffix_returns_none_when_auth_blob_is_none() -> None:
    """Missing ``auth_blob`` from the request body shouldn't blow up."""
    assert _derive_suffix(None) is None


@pytest.mark.unit
def test_derive_suffix_returns_none_when_auth_blob_is_not_a_dict() -> None:
    """A malformed body type → ``None``."""
    assert _derive_suffix("not a dict") is None  # type: ignore[arg-type]
