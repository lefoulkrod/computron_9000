"""
Tests for models package initialization.
"""

import pytest

import models


def test_package_exports():
    """Test that expected functions and classes are exported."""
    assert hasattr(models, "get_default_model")
    assert hasattr(models, "get_model_by_name")
    assert hasattr(models, "ModelNotFoundError")
