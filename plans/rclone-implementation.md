# Rclone Storage Integration — Implementation Plan

## Status: In Progress

### 1. Wire up `_VERB_CAPABILITY` + `_VERB_TYPES` for rclone verbs
- [ ] Add rclone verbs to `_VERB_CAPABILITY` in `broker_client/_verb_types.py`
- [ ] Add rclone verbs to `_VERB_TYPES` in `broker_client/_verb_types.py`

### 2. Add new verbs: search, cat, size
- [ ] Add `search`, `cat`, `size` verbs to `rclone_broker/_verbs.py`
- [ ] Add `search`, `cat`, `size` to rclone broker `_VERB_TYPE` dict
- [ ] Create `tools/integrations/rclone_search.py`
- [ ] Create `tools/integrations/rclone_cat.py`
- [ ] Create `tools/integrations/rclone_size.py`
- [ ] Add new verbs to `_VERB_CAPABILITY` and `_VERB_TYPES`

### 3. Tool registration
- [ ] Update `tools/integrations/__init__.py` to register rclone tools for "storage" capability
- [ ] Update server-side tool dispatch to expose storage tools

### 4. Tests
- [ ] Unit tests for rclone broker verbs (path validation, dispatch, write enforcement)
- [ ] Update drift test for multi-broker verb tables
- [ ] Integration test for rclone broker process

### 5. Cleanup
- [ ] Run existing tests to verify nothing is broken
- [ ] Final review