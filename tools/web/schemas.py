from pydantic import BaseModel

__all__ = [
    "GetWebpageResult",
    "GetWebpageError",
]

class GetWebpageResult(BaseModel):
    """
    Output model for the webpage content.

    Args:
        url (str): The URL that was fetched.
        html (str): The full HTML content of the page.
        response_code (int): The HTTP response code returned by the server.
    """
    url: str
    html: str
    response_code: int

class GetWebpageError(Exception):
    """
    Custom exception for get_webpage tool errors.
    """
    pass
