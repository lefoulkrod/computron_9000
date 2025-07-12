"""Tests for the datetime tool in tools.misc.datetime."""
import pytest

from tools.misc.datetime import datetime_tool, DateTimeResult

@pytest.mark.unit
def test_datetime_tool_success():
    """
    Test that datetime_tool returns a successful result with a non-empty datetime string and timezone.
    """
    result = datetime_tool()
    assert result.status == "success"
    assert result.datetime is not None
    assert len(result.datetime) > 0
    assert result.timezone is not None
    assert len(result.timezone) > 0
    assert result.error_message is None
