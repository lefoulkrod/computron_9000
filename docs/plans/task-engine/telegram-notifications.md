# Telegram Push Notifications for Task Engine

## Goal

When a goal run completes (or fails), send the final task output text and any
file attachments produced during the run to a Telegram chat. This is
one-way push messaging — no bot commands, no incoming messages.

## Architecture

```
TaskRunner._execute()
       │
       ├─ task completes/fails
       │
       ▼
TaskRunner._on_run_finished(run)
       │
       ├─ collect final task result text
       ├─ collect file_output paths from all tasks in the run
       │
       ▼
TelegramNotifier.send(message, attachments)
       │
       ▼
Telegram Bot API  (api.telegram.org)
  POST /bot{token}/sendMessage
  POST /bot{token}/sendDocument  (per attachment)
```

## Components

### 1. Telegram Bot (external setup)

The user creates a bot via @BotFather and gets a token. Then starts a
chat with the bot (or adds it to a group) to get the `chat_id`. We just
POST to the Bot API — no webhook server, no polling for updates.

### 2. Config

Secrets live in `.env` (already in `.gitignore`), behavior flags in `config.yaml`.

**.env:**
```bash
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...   # from @BotFather
TELEGRAM_CHAT_ID=987654321              # user's chat or group ID
```

**config.yaml:**
```yaml
goals:
  notifications:
    enabled: false
    on_run_completed: true       # send on successful completion
    on_run_failed: true          # send on failure
    include_files: true          # attach file outputs
    max_attachment_size_mb: 50   # Telegram limit is 50MB for bots
```

### 3. NotificationsConfig (config/__init__.py)

```python
class NotificationsConfig(BaseModel):
    enabled: bool = False
    on_run_completed: bool = True
    on_run_failed: bool = True
    include_files: bool = True
    max_attachment_size_mb: int = 50
```

Added as `GoalsConfig.notifications: NotificationsConfig`.

`TelegramNotifier` reads `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` from
`os.environ` at construction time. If either is missing when
`notifications.enabled` is true, it logs a warning and disables itself.

### 4. TelegramNotifier (tasks/_notifier.py)

Thin HTTP client that talks to the Telegram Bot API:

```python
class TelegramNotifier:
    """Sends messages and file attachments to Telegram via the Bot API."""

    def __init__(self, config: NotificationsConfig) -> None:
        self._config = config
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self._chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
        if not token or not self._chat_id:
            logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, notifications disabled")
            self._disabled = True
            self._base = ""
            return
        self._disabled = False
        self._base = f"https://api.telegram.org/bot{token}"

    async def send(
        self,
        message: str,
        attachments: list[Path] | None = None,
    ) -> None:
        """Send a message then each attachment as a separate document.

        POST /sendMessage for text, POST /sendDocument per file.
        Logs errors but never raises — notifications must not break the runner.
        """
```

Key behaviors:
- **Fire-and-forget** — errors are logged, never raised. Notifications must
  not break the task runner.
- **Text first, then files** — sends the message via `sendMessage`, then
  each file via `sendDocument` (multipart upload). Telegram limits
  `sendMessage` to 4096 chars, so long outputs are truncated with a note.
- **Size guard** — files exceeding `max_attachment_size_mb` are skipped with
  a note in the message.
- **Markdown formatting** — uses `parse_mode=MarkdownV2` for the message.
- Uses `httpx.AsyncClient` (already a dependency). No Telegram SDK needed.

### 5. Runner integration (tasks/_runner.py)

After `_execute` finishes and `update_run_status` returns a terminal status:

```python
async def _execute(self, task_result, task):
    # ... existing execution logic ...

    new_status = self._store.update_run_status(task_result.run_id)
    if new_status in ("completed", "failed") and self._notifier:
        await self._notify_run_finished(task_result.run_id, new_status)
```

The `_notify_run_finished` method:
1. Gets the run and goal from the store
2. Collects the result text from the **last task** in the run (the final
   output — typically a summary task that depends on all others)
3. Collects all `file_output` paths from completed task results
4. Formats a message: goal name, status, duration, final output excerpt
5. Calls `self._notifier.send(message, attachments)`

### 6. Collecting file outputs

File paths need to be available after the run completes. Two options:

**Option A — Store file paths on TaskResult (simpler):**
Add `file_outputs: list[str]` to the `TaskResult` model. The executor
collects `FileOutputPayload` events during the turn and writes the paths
to the task result when it completes. The notifier reads them from the store.

**Option B — Read from persisted conversation events:**
The `AgentEventBufferHook` already persists `file_output` events with
paths. The notifier could load the conversation events for each task
result and extract file paths. This avoids schema changes but adds I/O.

**Recommendation: Option A.** It's a single field addition, keeps the
notifier independent of the conversation storage layer, and the data is
already available in the executor (from the event dispatcher).

## Message Format

```
✅ Goal completed: Find the current price of Pop-Tarts
Run #2 · 47s · 3/3 tasks

Final output:
Pop-Tarts (8-count, Frosted Strawberry):
- Walmart: $3.48
- Target: $3.69
- Amazon: $4.29 (Subscribe & Save: $3.86)

📎 1 file attached
```

For failures:
```
❌ Goal failed: Find the current price of Pop-Tarts
Run #2 · 12s · 1/3 tasks completed

Error (task: Search for Pop-Tarts prices online):
ConnectionError: Failed to reach walmart.com after 3 retries
```

## File plan

| File | Change |
|---|---|
| `config/__init__.py` | Add `NotificationsConfig`, nest in `GoalsConfig` |
| `config.yaml` | Add `goals.notifications` section (disabled by default) |
| `tasks/_models.py` | Add `file_outputs: list[str]` to `TaskResult` |
| `tasks/_notifier.py` | New — `TelegramNotifier` class |
| `tasks/_runner.py` | Accept optional `TelegramNotifier`, call on run completion |
| `tasks/_executor.py` | Collect file output paths from events, return with result |
| `server/aiohttp_app.py` | Construct `TelegramNotifier` if enabled, pass to runner |
| `tests/tasks/test_notifier.py` | Unit tests with httpx mock |

## What this does NOT include

- No incoming message handling (no bot commands)
- No per-goal notification preferences (all-or-nothing via config)
- No message formatting customization
- No other messaging platforms (Signal, Slack, etc.)
