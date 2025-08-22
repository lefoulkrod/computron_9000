"""Unit tests for ModelConfig.options optional/normalization behavior."""
from __future__ import annotations

import pytest

from config import ModelConfig


@pytest.mark.unit
def test_options_defaults_to_empty_dict_when_missing() -> None:
    """Omitting options should result in an empty dict by default."""
    mc = ModelConfig(name="m1", model="dummy")
    assert isinstance(mc.options, dict)
    assert mc.options == {}


@pytest.mark.unit
def test_options_none_normalizes_to_empty_dict() -> None:
    """Explicit None in YAML should normalize to empty dict via validator."""
    mc = ModelConfig(name="m2", model="dummy", options=None)  # type: ignore[arg-type]
    assert mc.options == {}


@pytest.mark.unit
def test_options_preserves_mapping() -> None:
    """Provided mapping must be preserved unchanged."""
    opts = {"num_ctx": 1024, "temperature": 0.2}
    mc = ModelConfig(name="m3", model="dummy", options=opts)
    assert mc.options is opts or mc.options == opts


@pytest.mark.unit
def test_options_invalid_type_raises() -> None:
    """Non-mapping options should raise a TypeError from validator."""
    with pytest.raises(TypeError):
        _ = ModelConfig(name="m4", model="dummy", options=["not", "a", "mapping"])  # type: ignore[arg-type]
