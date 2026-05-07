"""Drift check between the broker's verb table and the broker_client's.

The broker's ``_VERB_TYPE`` (in ``integrations.brokers.email_broker._verbs``)
is the authoritative gate — it's what enforces WRITE_DENIED at the broker.
The broker_client keeps its own ``_VERB_TYPES`` so the app server can
classify a verb without reaching across the package boundary. This test
asserts the two stay in lockstep: adding a verb on one side without the
other (or changing its read/write tag) fails here, loudly, before it
reaches a developer or a user as a confusing mid-call error.
"""

from __future__ import annotations

import pytest

from integrations.broker_client._verb_types import _VERB_TYPES as CLIENT_TYPES
from integrations.brokers.email_broker._verbs import _VERB_TYPE as BROKER_TYPES


@pytest.mark.unit
def test_broker_and_client_verb_tables_agree() -> None:
    """The broker's verb table and the broker_client's must be identical.

    Equal as dicts — same keys, same values. A diff in either direction
    means one side has been edited and the other forgotten, which would
    let the app server permit a verb the broker rejects (or vice versa).
    """
    assert CLIENT_TYPES == BROKER_TYPES, (
        "verb-type drift: broker_client and broker disagree.\n"
        f"  only on broker_client: {sorted(set(CLIENT_TYPES) - set(BROKER_TYPES))}\n"
        f"  only on broker: {sorted(set(BROKER_TYPES) - set(CLIENT_TYPES))}\n"
        f"  type mismatches: "
        f"{sorted((k, CLIENT_TYPES[k], BROKER_TYPES[k]) for k in set(CLIENT_TYPES) & set(BROKER_TYPES) if CLIENT_TYPES[k] != BROKER_TYPES[k])}"
    )
