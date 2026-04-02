# Implementation Plan: Auto-Generated Conversation Titles

## Status: ✅ COMPLETED

## Summary of Changes

This implementation adds auto-generated conversation titles to improve the user experience in the ConversationsPanel.

### Files Modified

#### Backend Files

| File | Changes |
|------|---------|
| `conversations/_models.py` | ✅ Added `title: str` field to `ConversationSummary` model |
| `conversations/_store.py` | ✅ Added `save_conversation_title()` function, updated `list_conversations()` to load titles from metadata |
| `conversations/__init__.py` | ✅ Exported new `save_conversation_title` function |
| `server/aiohttp_app.py` | ✅ Added `POST /api/conversations/sessions/{conversation_id}/generate-title` endpoint |
| `server/message_handler.py` | ✅ Added `generate_conversation_title()` function using the summary model |

#### Frontend Files

| File | Changes |
|------|---------|
| `server/ui/src/components/ConversationsPanel.jsx` | ✅ Display `title` field with fallback to first_message |
| `server/ui/src/hooks/useStreamingChat.js` | ✅ Call title generation API after first message exchange completes |

#### Test Files

| File | Changes |
|------|---------|
| `tests/test_conversation_titles.py` | ✅ Added unit tests for ConversationSummary and title generation |

## Implementation Details

### 1. Conversation Summary Model
- Added `title: str = ""` field to `ConversationSummary` Pydantic model
- Backward compatible - defaults to empty string

### 2. Title Storage
- Created `save_conversation_title()` function that stores titles in `metadata.json` alongside conversation history
- Modified `list_conversations()` to read title from metadata
- Added `load_conversation_metadata()` helper function

### 3. Title Generation
- Uses the configured summary model from `config.yaml` (e.g., `qwen2.5:7b`)
- Prompt is optimized for generating concise, descriptive titles (3-5 words)
- Falls back to truncated message text if generation fails
- Non-blocking - runs after the first turn completes

### 4. API Endpoint
- `POST /api/conversations/sessions/{conversation_id}/generate-title`
- Loads conversation history, extracts first user message
- Generates title using summary model
- Saves title to metadata
- Returns generated title as JSON

### 5. Frontend Integration
- ConversationsPanel displays title if available, falls back to first_message
- useStreamingChat hook triggers title generation after first message exchange
- Uses setTimeout to avoid race conditions with conversation persistence

## Key Design Decisions

1. **Uses summary model**: Leverages the existing summary model configuration instead of adding a new one
2. **Non-blocking**: Title generation happens after the turn completes, not during user interaction
3. **Graceful fallback**: If generation fails, the UI falls back to displaying the first message
4. **Metadata storage**: Titles are stored in metadata.json alongside conversation history, keeping data organized

## Testing

All tests pass:
- `tests/test_conversation_titles.py` - 4 tests covering ConversationSummary model and title generation
- `tests/tools/conversations/` - 20 existing tests still pass
- `tests/sdk/context/` - conversation history tests still pass

## Success Criteria Checklist

- [x] Conversations display auto-generated titles in the sidebar
- [x] Titles are concise and descriptive
- [x] Fallback to first_message snippet works correctly
- [x] No errors when summary model is unavailable
- [x] Title generation is non-blocking (doesn't slow down chat)

## How to Test

1. Start a new conversation with a descriptive first message
2. Wait for the LLM response to complete
3. Check the ConversationsPanel - the conversation should display a generated title
4. The title will be auto-generated using the summary model (e.g., "Capital of France" for "What is the capital of France?")

## Rollback

This implementation is backward compatible. To roll back:
1. Revert the commits
2. The `title` field defaults to empty string, so existing code continues to work
3. Frontend gracefully falls back to first_message when title is empty
