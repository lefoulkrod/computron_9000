# Setup Readiness Gate

Some subsystems (like the task runner) need user-driven setup to complete
before they can do real work.  The setup module provides a readiness gate
that lets these subsystems wait without knowing what "setup" actually
involves.

## How it works

The aiohttp app (`server/aiohttp_app.py`) owns all the wiring. The gate is
an `asyncio.Event` stored as `app["ready"]`, and the app itself registers
the startup hooks that create it and the per-subsystem background tasks
that wait on it. Subsystem packages (`tasks/`, etc.) stay ignorant of the
ready signal.

### Startup flow

During `app.on_startup` (before the server begins accepting requests):

```
1. _run_data_migrations runs migrations synchronously
2. _init_ready_signal creates app["ready"] and checks setup.is_ready()
   - If True:  app["ready"] is set immediately
   - If False: app["ready"] stays unset
3. Per-subsystem startup hooks (e.g. _start_task_runner) spawn a
   background task that awaits app["ready"] before initializing
```

Then the server begins accepting requests. If `ready` wasn't set, the
background tasks block:

```
4. User completes the setup wizard in the browser
5. Settings handler calls setup.mark_ready(app)
6. app["ready"] fires, waiting tasks proceed
```

If the setup wizard was already completed in a previous session,
step 2 sets the event immediately and subsystems start without waiting.

### Adding a new deferred subsystem

Add a startup hook in `server/aiohttp_app.py` that spawns a background
task and waits on `app["ready"]` before initializing the subsystem, plus
a cleanup hook that cancels the init task. See `_start_task_runner` /
`_stop_task_runner` in `server/aiohttp_app.py` for the reference
implementation.

## The setup module

The `setup` package re-exports two functions:

- **`is_ready() -> bool`** — Returns True if all prerequisites are met.
  Today this checks `setup_complete` in settings.  To add a new
  prerequisite, add another check here.

- **`mark_ready(app)`** — Called when a prerequisite is fulfilled (e.g.
  the settings handler detects `setup_complete` just flipped to True).
  Re-checks `is_ready()` before firing the event, so the signal only
  fires when *all* prerequisites are satisfied.

Both are defined in `setup/_gate.py` and re-exported from
`setup/__init__.py`.

## Adding a new prerequisite

1. Add a check in `is_ready()` (in `setup/_gate.py`):

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
