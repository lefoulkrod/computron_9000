# Data Migrations

Data migrations transform on-disk state when the application is upgraded.
They run once at startup, before the server accepts requests, and require
no user interaction.

## When to use a migration

Use a migration when you need to change the shape of persisted data — renaming
fields, restructuring JSON files, populating new default data, etc.  If the
change only affects code (not stored state), you don't need a migration.

## How they work

1. The server calls `run_migrations(state_dir)` during its `on_startup` phase,
   before the HTTP server begins listening.
2. The runner loads `.migrations.json` from the state directory to see which
   migrations have already been applied.
3. It walks the registered migration list in order and runs any that haven't
   been applied yet.
4. After each migration succeeds, its name is appended to `.migrations.json`
   so it won't run again.

Migrations are synchronous and blocking — the app won't start until they
finish.  Keep them fast.

## Adding a new migration

1. Create a new file in `migrations/`, following the naming convention
   `_NNN_short_description.py` (e.g. `_003_add_profile_version.py`).

2. Import the `_register` decorator from `migrations._runner` and decorate
   your migration function:

   ```python
   from migrations._runner import _register

   @_register("003_add_profile_version")
   def migrate(state_dir: Path) -> None:
       # state_dir is the root state directory (~/.computron_9000/)
       ...
   ```

3. Import your migration module in `migrations/_runner.py` inside
   `run_migrations()`:

   ```python
   import migrations._003_add_profile_version  # noqa: F401
   ```

   The import triggers the `@_register` decorator, which adds the migration
   to the runner's list.

## Guidelines

- **Back up before modifying.** If you're rewriting files, save a copy first
  (see `_001_task_agent_to_profile.py` for the pattern).
- **Be idempotent within the migration.** If a file has already been partially
  migrated (e.g. from a crash), handle that gracefully.
- **Don't import application code that has side effects.** Migrations run
  early in startup.  Importing heavy modules (LLM providers, browser tools)
  can cause problems.  Stick to stdlib + config.
- **Keep migrations fast.** They block startup.

## File layout

```
migrations/
  __init__.py                         # re-exports run_migrations
  _runner.py                          # discovers and applies migrations
  _001_task_agent_to_profile.py       # example: field rename
  _002_install_default_profiles.py    # example: seed default data
```

## Tracking file

Applied migrations are recorded in `{state_dir}/.migrations.json`:

```json
[
  "001_task_agent_to_profile",
  "002_install_default_profiles"
]
```

Delete an entry from this file to re-run a migration (useful during
development).
