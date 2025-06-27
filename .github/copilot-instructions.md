````instructions
# Copilot Custom Instructions

- Format Python imports per PEP 8: standard first, then third-party, then local (blank line between groups)
- Use Google-style docstrings with Args/Returns/Raises sections
- Add type hints to all function signatures
- Prefer async/await for I/O-bound operations
- Use f-strings for string formatting
- Maintain existing directory structure
- Place business logic in appropriate packages (e.g., agents/adk/)
- Keep functions/classes small and focused
- Handle exceptions with context-aware logging
- Use custom exceptions when appropriate
- Write tests for new features/bug fixes
- Use descriptive test names and docstrings
- Document all public APIs
- Update README/doc files with new features
- Add dependencies to pyproject.toml
- Use minimal well-maintained libraries
- Validate API inputs
- Avoid hardcoded secrets
- Use Pydantic for data validation
- Ensure JSON serializable API responses
- Use single leading underscore for private fields/methods
- Use module-level logger (logger = logging.getLogger(__name__))
- Use __init__.py for public re-exports
- Place tests in tests/ directory matching source structure

Example import order:
```python
import os
import sys

import aiohttp
import pydantic

from myproject.module import MyClass
```

Example Google style docstring:
```python
def foo(bar: int) -> str:
    """
    Brief description of the function.

    Args:
        bar (int): Description of the argument.

    Returns:
        str: Description of the return value.
    """
````
