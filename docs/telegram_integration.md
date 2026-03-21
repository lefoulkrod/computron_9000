# Telegram Integration

## Goal

Turn Computron from a reactive assistant into a proactive worker. Users can interact with Computron through Telegram — send messages, receive responses, get notified when background jobs complete, and receive file deliverables (PDFs, audio, images) as native Telegram attachments.

## Architecture Overview

```
┌──────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   Telegram   │◄───►│  Telegram        │────►│  message_handler │
│   (user)     │     │  Adapter          │◄────│  (existing)      │
└──────────────┘     └──────────────────┘     └──────────────────┘
                            │                         │
                            │                         ▼
                            │                  ┌──────────────────┐
                            │                  │  Agent Loop      │
                            │                  │  (existing)      │
                            └──────────────────┤                  │
                           subscribes to events│  publish_event() │
                                               └──────────────────┘

                     ┌──────────────────┐
                     │  Job Scheduler   │───► runs jobs on schedule
                     │  (new)           │───► creates conversations
                     └──────────────────┘───► triggers agent loop
```

## Components

### 1. Telegram Bot Adapter

A thin transport layer that bridges Telegram messages to the existing `handle_user_message()` pipeline and routes responses back.

**Receiving messages:**
- Long-poll Telegram's `getUpdates` API (no webhook server needed — keeps infra simple)
- Map each Telegram chat to a Computron conversation ID (e.g. `telegram:{chat_id}`)
- Call `handle_user_message()` with the text, consuming the `AssistantResponse` async generator
- Telegram file attachments → Computron `Data` objects (photos, documents, voice)

**Sending responses:**
- Subscribe to the `AssistantResponse` event stream from `handle_user_message()`
- Buffer `content` chunks and send as a single Telegram message on `final=True`
- Handle event payloads:
  - `FileOutputPayload` → `sendDocument` / `sendAudio` / `sendPhoto` based on content_type
  - `BrowserScreenshotPayload` → `sendPhoto`
  - `AudioPlaybackPayload` → `sendAudio` / `sendVoice`
  - Other events → skip or format as status text

**Message formatting:**
- Telegram supports Markdown (MarkdownV2 mode) — map from the agent's markdown output
- Long messages (>4096 chars) need to be split at paragraph boundaries
- Code blocks, links, bold/italic all carry over naturally

**Location:** `server/telegram/` (new module)

**Dependencies:** `httpx` (already in project) — no telegram-specific library needed. The Bot API is simple enough to call directly.

### 2. Background Job System

Decouples task execution from the request/response cycle so jobs can run without an active client connection.

**Job model:**
```python
@dataclass
class Job:
    id: str
    conversation_id: str
    instructions: str          # what to tell the agent
    agent: str                 # which agent to use (default: computron)
    schedule: str | None       # cron expression, or None for one-shot
    channel: str               # "telegram" (future: "sms", "web")
    channel_id: str            # telegram chat_id
    model: str                 # which LLM model to use
    status: str                # pending | running | completed | failed
    created_at: datetime
    last_run_at: datetime | None
    next_run_at: datetime | None
```

**Execution:**
- One-shot jobs: `asyncio.create_task()` from the Telegram adapter when the agent decides to background a task
- Scheduled jobs: a lightweight scheduler loop checks `next_run_at` every minute, fires due jobs
- Each job run creates a conversation context, calls `handle_user_message()`, collects results
- On completion/failure: send notification via the job's channel

**Persistence:**
- Store jobs as JSON files in a `jobs/` directory (same pattern as conversation history)
- Survives server restarts — scheduler loads pending/scheduled jobs on startup

**Location:** `jobs/` (new module)

### 3. Agent Integration

The agent needs to be able to create background jobs and scheduled tasks. New tools:

```python
def schedule_job(
    instructions: str,
    schedule: str | None = None,  # cron expression like "0 7 * * *"
    description: str = "",
) -> str:
    """Schedule a background job. If schedule is None, runs once immediately in the background."""

def list_jobs() -> str:
    """List all active and scheduled jobs."""

def cancel_job(job_id: str) -> str:
    """Cancel a scheduled or running job."""
```

The agent doesn't need to know about Telegram directly — it just creates jobs. The job system knows which channel initiated the conversation and delivers results there.

### 4. Notification Delivery

When a background job completes, the notification includes:
- A text summary of what was done
- Any file deliverables as attachments
- A reference to the conversation so the user can follow up

**Collecting deliverables:** The job runner subscribes to events during execution and captures `FileOutputPayload`, `AudioPlaybackPayload`, etc. After the agent loop completes, it sends the summary + collected files via the appropriate channel.

## Configuration

```yaml
# config.yaml
telegram:
  bot_token: ${TELEGRAM_BOT_TOKEN}    # env var reference
  allowed_chat_ids:                    # restrict access to specific users
    - "123456789"
```

- `TELEGRAM_BOT_TOKEN` — from BotFather, stored as env var (not in config file)
- `allowed_chat_ids` — whitelist of Telegram user/chat IDs that can interact with the bot. Reject messages from unknown chat IDs.

## Telegram Bot Setup

One-time setup:
1. Message @BotFather on Telegram, `/newbot`, follow prompts
2. Copy the bot token, set as `TELEGRAM_BOT_TOKEN` env var
3. Message the bot from your Telegram account
4. Get your chat ID: `curl https://api.telegram.org/bot<token>/getUpdates`
5. Add your chat ID to `allowed_chat_ids` in config

## Example Flows

### Interactive conversation
```
User (Telegram):  "what's the weather in SF?"
Computron:         "Currently 62F and foggy in San Francisco."
```

### Background job
```
User (Telegram):  "research the top 5 vector databases and write a comparison.
                   take your time"
Computron:         "On it — I'll message you when the comparison is ready."
[... 10 minutes later ...]
Computron:         "Done. Here's the comparison summary: ..."
Computron:         [sends comparison.pdf]
```

### Scheduled job
```
User (Telegram):  "every morning at 7am, summarize the top HN stories for me"
Computron:         "Scheduled. I'll send you a daily HN digest at 7:00 AM."
[... next morning at 7:00 AM ...]
Computron:         "Good morning. Here's today's HN digest: ..."
```

## Implementation Plan

### Phase 1: Telegram send-only + background jobs
- Telegram adapter (send only — `sendMessage`, `sendDocument`)
- Background job runner with `asyncio.create_task()`
- `schedule_job` / `list_jobs` / `cancel_job` agent tools
- Notification delivery on job completion
- Job persistence (JSON files)

### Phase 2: Telegram receive (interactive)
- `getUpdates` polling loop
- Message routing to `handle_user_message()`
- Conversation mapping (telegram chat → conversation ID)
- Access control via `allowed_chat_ids`
- File attachment handling (telegram → Computron)

### Phase 3: Scheduled jobs
- Cron-based scheduler loop
- Schedule persistence and reload on startup
- Job management (list, cancel, modify schedule)

### Phase 4: Rich interactions
- Inline keyboards for confirmations ("Run this job now? [Yes] [No]")
- Progress updates for long-running jobs
- Reply-to-message threading for multi-turn conversations
- Voice message input (Telegram voice → speech-to-text → agent)

## Open Questions

- **Multiple users?** Currently designed for single-user. If multiple Telegram users interact, each gets isolated conversations via chat ID, but they share the same Ollama instance and compute resources.
- **Job concurrency?** How many background jobs can run simultaneously? Depends on Ollama `NUM_PARALLEL` and VRAM. May need a job queue with concurrency limits.
- **Long messages?** Agent responses can be very long. Split into multiple Telegram messages? Truncate and attach full response as a file?
- **Error handling?** If a scheduled job fails repeatedly, should it be auto-disabled? Notify with error details?
