# Copilot Custom Instructions

- Always format Python imports according to PEP 8:
  - Standard library imports first, then third-party, then local imports.
  - Each group separated by a blank line.
  - Imports within each group should be alphabetized.
- Always use Google style docstrings for all functions, classes, and modules:
  - Include Args, Returns, and Raises sections as appropriate.
  - Be clear and concise, but provide enough detail for users and tools.
- Use type hints for all function signatures.
- Prefer async/await for I/O-bound operations.
- Use f-strings for string formatting.
- Follow the existing directory and module structure.
- Place new business logic in the appropriate package (e.g., agents/adk/ for agent logic).
- Keep functions and classes small and focused.
- Always handle exceptions gracefully and log errors with enough context.
- Use custom exceptions where appropriate.
- Write tests for new features and bug fixes.
- Use descriptive test names and docstrings.
- Document all public functions, classes, and modules.
- Update the README and relevant doc files when adding features.
- Add new dependencies to pyproject.toml and keep them up to date.
- Prefer minimal and well-maintained libraries.
- Validate all user input, especially in API endpoints.
- Avoid hardcoding secrets or credentials.
- Use Pydantic models for all data validation and serialization.
- Ensure all API responses are JSON serializable.
- Always use a single leading underscore (_) for private fields and methods, following PEP 8 recommendations:
  - See: https://peps.python.org/pep-0008/#descriptive-naming-styles
  - Use a single leading underscore for non-public methods and instance variables (e.g., _my_private_var).
  - Use two leading underscores only when name mangling is required to avoid subclass conflicts.

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
```
