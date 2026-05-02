# Rclone Integration — Remaining Work

## Status: Complete ✅

## Completed
- [x] Rclone broker implementation (`integrations/brokers/rclone_broker/`)
- [x] 9 agent tools (`tools/integrations/rclone_*.py`)
- [x] Tool registration in `sdk/tools/_core.py` (storage capability gating)
- [x] Verb types (`integrations/broker_client/_verb_types.py`)
- [x] Drift test (`tests/integrations/test_verb_types_drift.py`)
- [x] Rclone verb unit tests (30 tests including all 12 verbs, path validation, local path validation, truncation, error cases)
- [x] Catalog with multi-broker entries (`integrations/supervisor/_catalog.py`)
- [x] Multi-broker architecture (`IntegrationRecord.brokers: dict[str, BrokerHandle]`)
- [x] App sock handler with capability routing (`_app_sock.py`)
- [x] UI: AddIntegrationModal with capability checkboxes
- [x] UI: IntegrationsTab with capability labels
- [x] Dockerfile: rclone installed from .deb
- [x] API routes: `enabled_capabilities` passed through
- [x] broker_client call routing by capability
- [x] Multi-broker supervisor tests (12 tests: resolve, add, record_to_dict)
- [x] Broker_client capability routing tests (7 tests: email/storage routing, unknown verbs, capability-not-found)
- [x] All 177 integration tests passing