# PR: improvement: implement OpenAI provider stub with explicit method signatures

## Summary
This PR expands the `OpenAIProvider` class from a minimal 7-line stub to a complete 40-line implementation with explicit method signatures.

## Changes Made

**File:** `sdk/providers/_openai.py`

### What Changed (Lines 1-40)

1. **Added imports (Lines 3-7):**
   - `from collections.abc import AsyncGenerator, Callable`
   - `from typing import Any`
   - `from ._models import ChatDelta, ChatResponse`

2. **Implemented `chat()` method (Lines 13-23):**
   - Added full type signature with parameters: `model`, `messages`, `tools`, `options`, `think`
   - Returns `ChatResponse`
   - Raises `NotImplementedError` with clear message

3. **Implemented `chat_stream()` method (Lines 25-36):**
   - Added full async generator signature matching base class
   - Returns `AsyncGenerator[ChatDelta | ChatResponse, None]`
   - Raises `NotImplementedError` with clear message

4. **Implemented `list_models()` method (Lines 38-40):**
   - Returns `list[str]`
   - Raises `NotImplementedError` with clear message

## Why This Is an Improvement

The original 7-line stub was incomplete and would cause runtime errors or type checker warnings when used. This implementation:
- Provides explicit method signatures that match the abstract base class `BaseAPIProvider`
- Makes the "not yet implemented" status explicit to developers
- Enables proper IDE autocomplete and type checking
- Follows the same pattern as other provider stubs in the codebase

## Testing

All 6 tests in `tests/sdk/providers/test_provider_factory.py` pass:
- `test_create_openai_provider` - Factory can create OpenAIProvider instance
- `test_provider_factory_caches_instances` - Factory caching works correctly
- `test_provider_factory_returns_correct_provider_class` - Correct provider class returned
- `test_provider_factory_raises_error_for_invalid_provider` - Invalid provider handling works
- `test_provider_factory_raises_error_for_unsupported_provider` - Unsupported provider handling works
- `test_get_supported_providers_returns_expected_list` - Supported providers list is correct

## Related Code

The `OpenAIProvider` now properly extends `BaseAPIProvider` with explicit stubs for all required abstract methods, following the same pattern as other provider implementations in the SDK.
