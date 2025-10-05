from __future__ import annotations

import pytest
import logging
from typing import Any, TYPE_CHECKING

import types
import asyncio

from tools.browser.core._dom_utils import _element_bool_state
from playwright.async_api import Error as PlaywrightError

if TYPE_CHECKING:
    # Use pytest's internal LogCaptureFixture type for static typing only; avoid runtime import
    from _pytest.logging import LogCaptureFixture


class _PropTrueHandle:
    async def evaluate(self, script: str) -> Any:  # returns proper boolean
        assert 'checked' in script or 'selected' in script or '=>' in script
        return True

    async def get_attribute(self, name: str) -> Any:  # should not be called in this case
        raise AssertionError("get_attribute should not be reached when evaluate returns bool")


class _PropNonBoolAttrPresentHandle:
    async def evaluate(self, script: str) -> Any:  # returns a non-bool value forcing fallback
        return "yes"  # truthy but not bool -> should ignore

    async def get_attribute(self, name: str) -> Any:
        if name == 'checked':
            return ""  # presence => True
        return None


class _PropErrorAttrMissingHandle:
    def __init__(self, raise_in_attr: bool = False):
        self.raise_in_attr = raise_in_attr

    async def evaluate(self, script: str) -> Any:
        # Simulate a Playwright evaluation failure so the helper logs and falls back
        raise PlaywrightError("boom")

    async def get_attribute(self, name: str) -> Any:
        if self.raise_in_attr:
            raise PlaywrightError("attr fail")
        return None  # missing attribute => False path leading to default


class _NoMethodsHandle:
    # Intentionally no evaluate/get_attribute
    pass


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bool_helper_property_true_short_circuits() -> None:
    handle = _PropTrueHandle()
    result = await _element_bool_state(handle, prop_script="el => el.checked === true", attr="checked", default=False, context="checkbox")
    assert result is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bool_helper_fallback_to_attribute_on_non_boolean_property_result() -> None:
    handle = _PropNonBoolAttrPresentHandle()
    result = await _element_bool_state(handle, prop_script="el => el.checked === true", attr="checked", default=False, context="checkbox")
    assert result is True  # attribute presence


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bool_helper_attribute_missing_returns_default() -> None:
    handle = _PropErrorAttrMissingHandle()
    result = await _element_bool_state(handle, prop_script="el => el.checked === true", attr="checked", default=False, context="checkbox")
    assert result is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bool_helper_attribute_error_returns_default_with_logging(caplog: LogCaptureFixture) -> None:
    handle = _PropErrorAttrMissingHandle(raise_in_attr=True)
    with caplog.at_level(logging.DEBUG):
        result = await _element_bool_state(handle, prop_script="el => el.checked === true", attr="checked", default=True, context="checkbox")
    assert result is True
    # Ensure a debug log mentioning attribute read failed or returning default
    assert any("returning default" in msg for msg in caplog.messages)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bool_helper_no_methods_returns_default_with_logging(caplog: LogCaptureFixture) -> None:
    handle = _NoMethodsHandle()
    with caplog.at_level(logging.DEBUG):
        result = await _element_bool_state(handle, prop_script="el => el.checked === true", attr="checked", default=True, context="checkbox")
    assert result is True
    assert any("No attribute reader available" in msg for msg in caplog.messages)
