"""Unit tests for helpers in ``server._integrations_routes``.

The route handlers themselves require a running supervisor on a UDS — those
go through the integration-tier suite (``tests/integrations``). The pure
helpers (``_derive_suffix_from_email``) are tested directly here.
"""

from __future__ import annotations

import pytest

from server._integrations_routes import _derive_suffix_from_email


# ── _derive_suffix_from_email ────────────────────────────────────────────────


@pytest.mark.unit
def test_derive_suffix_from_email_returns_local_part_for_simple_address() -> None:
    """A clean ASCII address → its local-part verbatim, lowercased.

    The local-part is what disambiguates two integrations of the same provider
    (``personal@`` vs ``work@``), so it's the natural suffix source.
    """
    assert _derive_suffix_from_email({"email": "alice@example.com"}) == "alice"


@pytest.mark.unit
def test_derive_suffix_from_email_lowercases() -> None:
    """Mixed-case input lowercases — the supervisor's regex demands ``[a-z]``,
    not ``[A-Za-z]``, so the route must normalize before forwarding.
    """
    assert _derive_suffix_from_email({"email": "Alice@Example.com"}) == "alice"


@pytest.mark.unit
def test_derive_suffix_from_email_replaces_dots_and_pluses_with_dashes() -> None:
    """``.`` and ``+`` are common in email local-parts (subaddressing,
    name.surname) and aren't in ``[a-z0-9_-]``. Each non-allowed char becomes
    a single ``-`` after the dash-run collapse.
    """
    assert _derive_suffix_from_email({"email": "alice.smith+work@x.com"}) == "alice-smith-work"


@pytest.mark.unit
def test_derive_suffix_from_email_collapses_dash_runs() -> None:
    """Multiple disallowed chars in a row don't produce ``--``; the run is
    collapsed to a single ``-`` so the output stays readable as an ID.
    """
    assert _derive_suffix_from_email({"email": "a..b@x.com"}) == "a-b"


@pytest.mark.unit
def test_derive_suffix_from_email_strips_leading_and_trailing_dashes() -> None:
    """Edges of the local-part shouldn't leak ``-`` boundaries — they make
    ugly IDs (e.g. ``icloud_-alice-`` vs ``icloud_alice``) and the dashes
    convey nothing.
    """
    assert _derive_suffix_from_email({"email": "-alice-@x.com"}) == "alice"


@pytest.mark.unit
def test_derive_suffix_from_email_preserves_underscore_and_dash() -> None:
    """``_`` and ``-`` are already in the allowed set — leave them alone."""
    assert _derive_suffix_from_email({"email": "alice_smith-2@x.com"}) == "alice_smith-2"


@pytest.mark.unit
def test_derive_suffix_from_email_caps_at_48_chars() -> None:
    """The supervisor's regex limits user_suffix to 48 chars; truncate
    pre-emptively rather than let the supervisor reject a long address.
    """
    long_local = "a" * 100
    out = _derive_suffix_from_email({"email": f"{long_local}@x.com"})
    assert out is not None
    assert len(out) == 48
    assert out == "a" * 48


@pytest.mark.unit
def test_derive_suffix_from_email_returns_none_when_local_is_all_disallowed() -> None:
    """If sanitization eats everything (e.g. ``++@``), there's nothing useful
    to use as a suffix — return ``None`` so the route handler can 400 with
    a clear message instead of forwarding an empty string.
    """
    assert _derive_suffix_from_email({"email": "++@x.com"}) is None


@pytest.mark.unit
def test_derive_suffix_from_email_handles_address_without_at_sign() -> None:
    """Some odd inputs (test fixtures, malformed addresses) lack ``@``.
    ``split("@", 1)[0]`` returns the whole string; we still sanitize.
    """
    assert _derive_suffix_from_email({"email": "noatsign"}) == "noatsign"


@pytest.mark.unit
def test_derive_suffix_from_email_returns_none_when_email_missing() -> None:
    """``auth_blob`` may not contain an ``email`` key for non-email
    integrations (future GitHub, Stripe, etc.). The helper returns ``None``
    rather than guessing — the route's email-required check fires next.
    """
    assert _derive_suffix_from_email({}) is None


@pytest.mark.unit
def test_derive_suffix_from_email_returns_none_when_email_not_a_string() -> None:
    """Defensive: a non-string ``email`` field shouldn't crash the route."""
    assert _derive_suffix_from_email({"email": 123}) is None  # type: ignore[arg-type]


@pytest.mark.unit
def test_derive_suffix_from_email_returns_none_when_auth_blob_is_none() -> None:
    """Missing ``auth_blob`` from the request body shouldn't blow up — the
    route then surfaces a clean BAD_REQUEST.
    """
    assert _derive_suffix_from_email(None) is None


@pytest.mark.unit
def test_derive_suffix_from_email_returns_none_when_auth_blob_is_not_a_dict() -> None:
    """Same defensive shape: a malformed body type → ``None``."""
    assert _derive_suffix_from_email("not a dict") is None  # type: ignore[arg-type]
