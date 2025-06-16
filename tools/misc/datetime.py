# Standard library imports
"""Tool for retrieving the current system date and time in human-readable 12-hour format."""
import datetime
import logging
from typing import Optional

# Third-party imports
from pydantic import BaseModel

class DateTimeResult(BaseModel):
    """Result model for the datetime tool."""
    
    status: str
    datetime: Optional[str] = None
    timezone: Optional[str] = None
    error_message: Optional[str] = None

def datetime_tool() -> DateTimeResult:
    """
    Get the current system date and time in human-readable 12-hour format (up to seconds), including timezone.

    Returns:
        DateTimeResult: Result object containing the formatted date and time string, timezone, or error details.
    """
    try:
        now = datetime.datetime.now(datetime.timezone.utc).astimezone()
        formatted = now.strftime('%I:%M:%S %p, %B %d, %Y')
        tzname = now.tzname() or 'Unknown'
        return DateTimeResult(status="success", datetime=formatted, timezone=tzname)
    except Exception as e:
        logging.error(f"Failed to get system datetime: {e}")
        return DateTimeResult(status="error", error_message=str(e))
