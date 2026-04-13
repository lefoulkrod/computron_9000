# Setup Readiness Gate

Some subsystems (like the task runner) need user-driven setup to complete
before they can do real work.  The setup module provides a readiness gate
that lets these subsystems wait without knowing what "setup" actually
involves.

## How it works

The gate is an `asyncio.Event` stored on the aiohttp app as `app["ready"]`.

### Startup flow

During `app.on_startup` (before the server begins accepting requests):

```
1. Migrations run (synchronous, no user interaction needed)
2. _init_ready_signal creates app["ready"] and checks setup.is_ready()
   - If True:  app["ready"] is set immediately
   - If False: app["ready"] stays unset
3. Subsystems spawn background tasks that await app["ready"]
```

Then the server begins accepting requests. Subsystems whose `ready` event
was not set block inside their background task:

```
4. User completes the setup wizard in the browser
5. Settings handler calls setup.mark_ready(app)
6. app["ready"] fires, waiting subsystems proceed
```

If the setup wizard was already completed in a previous session,
step 2 sets the event immediately and subsystems start without waiting.

### Subsystem pattern

Subsystems that need to wait for setup use a background task:

```python
async def _start_my_subsystem(app):
    async def _deferred():
        try:
            await app["ready"].wait()
            # now safe to initialize and run
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to start my_subsystem")

    app["_my_subsystem_init"] = asyncio.create_task(_deferred())
```

And a cleanup handler that cancels the waiting task if the app shuts
down before setup completes:

```python
async def _stop_my_subsystem(app):
    init_task = app.get("_my_subsystem_init")
    if init_task and not init_task.done():
        init_task.cancel()
    subsystem = app.get("my_subsystem")
    if subsystem:
        await subsystem.stop()
```

## The setup module

`setup/__init__.py` has two functions:

- **`is_ready() -> bool`** — Returns True if all prerequisites are met.
  Today this checks `setup_complete` in settings.  To add a new
  prerequisite, add another check here.

- **`mark_ready(app)`** — Called when a prerequisite is fulfilled (e.g.
  the settings handler detects `setup_complete` just flipped to True).
  Re-checks `is_ready()` before firing the event, so the signal only
  fires when *all* prerequisites are satisfied.

## Adding a new prerequisite

1. Add a check in `setup.is_ready()`:

   ```python
   def is_ready() -> bool:
       if not load_settings().get("setup_complete"):
           return False
       if not _model_is_available():  # new check
           return False
       return True
   ```

2. Call `setup.mark_ready(app)` from wherever that prerequisite gets
   fulfilled.  The `mark_ready` function is safe to call multiple times —
   it only fires the event when `is_ready()` returns True.

## Relationship to migrations

Migrations and setup are different things:

| | Migrations | Setup |
|---|---|---|
| **When** | Before server starts | After server is running |
| **Blocking** | Yes — app won't start | No — HTTP works, subsystems wait |
| **User interaction** | None | May require (e.g. setup wizard) |
| **Purpose** | Transform stored data | Ensure runtime prerequisites |

Both run at startup, but migrations are a hard gate on the entire app while
setup is a soft gate on optional subsystems.
