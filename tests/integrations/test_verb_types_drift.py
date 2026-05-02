"""Drift checks between broker verb tables and the broker_client's.

Each broker keeps its own ``_VERB_TYPE`` dict (the authoritative gate for
read/write enforcement). The broker_client keeps a combined ``_VERB_TYPES``
and ``_VERB_CAPABILITY`` so the app server can classify verbs and route
them to the right broker without reaching across package boundaries.

These tests assert the tables stay in sync: adding a verb on one side
without the other (or changing its read/write tag) fails loudly.
"""

from __future__ import annotations

import pytest

from integrations.broker_client._verb_types import _VERB_CAPABILITY, _VERB_TYPES as CLIENT_TYPES
from integrations.brokers.email_broker._verbs import _VERB_TYPE as EMAIL_TYPES
from integrations.brokers.rclone_broker._verbs import _VERB_TYPE as RCLONE_TYPES


@pytest.mark.unit
def test_client_verb_types_are_union_of_broker_verb_types() -> None:
    """The client's _VERB_TYPES must be the union of all broker _VERB_TYPE dicts.

    Every verb declared by any broker must appear in the client table with
    the same read/write tag. Verbs in the client table that no broker declares
    are also an error — they'd route to a broker that doesn't know them.
    """
    broker_union = {}
    broker_union.update(EMAIL_TYPES)
    broker_union.update(RCLONE_TYPES)

    assert CLIENT_TYPES == broker_union, (
        "verb-type drift: broker_client and brokers disagree.\n"
        f"  only in client: {sorted(set(CLIENT_TYPES) - set(broker_union))}\n"
        f"  only in brokers: {sorted(set(broker_union) - set(CLIENT_TYPES))}\n"
        f"  type mismatches: "
        f"{sorted((k, CLIENT_TYPES[k], broker_union[k]) for k in set(CLIENT_TYPES) & set(broker_union) if CLIENT_TYPES[k] != broker_union[k])}"
    )


@pytest.mark.unit
def test_verb_capability_keys_match_verb_types_keys() -> None:
    """_VERB_CAPABILITY must have exactly the same keys as _VERB_TYPES.

    Every verb must have a capability mapping. A mismatch means a verb
    was added to _VERB_TYPES but not to _VERB_CAPABILITY (or vice versa),
    which would cause call() to fail with "unknown verb".
    """
    assert set(_VERB_CAPABILITY.keys()) == set(CLIENT_TYPES.keys()), (
        "verb-capability drift: _VERB_CAPABILITY and _VERB_TYPES have different keys.\n"
        f"  only in _VERB_TYPES: {sorted(set(CLIENT_TYPES) - set(_VERB_CAPABILITY))}\n"
        f"  only in _VERB_CAPABILITY: {sorted(set(_VERB_CAPABILITY) - set(CLIENT_TYPES))}"
    )


@pytest.mark.unit
def test_capability_values_are_valid() -> None:
    """Every capability in _VERB_CAPABILITY must map to a known broker."""
    known_capabilities = {"email_calendar", "storage"}
    unknown = set(_VERB_CAPABILITY.values()) - known_capabilities
    assert not unknown, (
        f"unknown capabilities in _VERB_CAPABILITY: {sorted(unknown)}. "
        f"Known capabilities: {sorted(known_capabilities)}"
    )
