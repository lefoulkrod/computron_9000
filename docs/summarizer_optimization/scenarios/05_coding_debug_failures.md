# Scenario 05: Coding Debug with Failed Attempts

## Purpose

Tests that failed fix attempts and their specific failure modes survive compaction. This is the most critical scenario for the "process narration" debate — for coding agents, knowing what was tried and WHY it failed is essential to avoid retrying the same broken approach.

## Agent Type

COMPUTER_AGENT

## Conversation

User reports an API endpoint returning 500 errors. Agent investigates, tries two fixes that fail for different reasons, then finds the actual bug on the third attempt.

```
system: You are a coding assistant with file and terminal tools.

user: The /api/users/export endpoint is returning 500 errors in production. The error started after yesterday's deploy. Logs show "TypeError: cannot unpack non-sequence NoneType" in export_handler.py. Please fix it.

A: Let me look at the export handler code and the recent changes.
  [Called tools: read_file]

tool (read_file): File: /home/computron/webapp/handlers/export_handler.py
  1  import csv
  2  import io
  3  from datetime import datetime
  4
  5  from webapp.models import User, UserPreferences
  6  from webapp.auth import require_admin
  7
  8
  9  @require_admin
  10 async def export_users(request):
  11     """Export all users as CSV."""
  12     format_type = request.query.get("format", "csv")
  13     include_prefs = request.query.get("include_prefs", "false") == "true"
  14
  15     users = await User.all()
  16     rows = []
  17     for user in users:
  18         name, email = user.name, user.email
  19         created = user.created_at.strftime("%Y-%m-%d")
  20         if include_prefs:
  21             prefs = await UserPreferences.get(user_id=user.id)
  22             theme, lang = prefs.theme, prefs.language
  23             rows.append([name, email, created, theme, lang])
  24         else:
  25             rows.append([name, email, created])
  26
  27     output = io.StringIO()
  28     writer = csv.writer(output)
  29     writer.writerow(["Name", "Email", "Created"] +
  30                     (["Theme", "Language"] if include_prefs else []))
  31     writer.writerows(rows)
  32
  33     return web.Response(
  34         text=output.getvalue(),
  35         content_type="text/csv",
  36         headers={"Content-Disposition": "attachment; filename=users.csv"},
  37     )

A: I can see the issue. On line 22, `UserPreferences.get(user_id=user.id)` returns `None` when a user has no preferences record, and then line 23 tries to unpack `prefs.theme, prefs.language` on a None object. Let me check what changed yesterday.
  [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ cd /home/computron/webapp && git log --oneline -5
  a3f8c21 Add include_prefs query param to export endpoint
  b7d9e44 Update user model with email validation
  c12a567 Fix login rate limiting
  d45e890 Add admin dashboard metrics
  e67f123 Refactor auth middleware

A: The commit `a3f8c21` added the `include_prefs` parameter yesterday. That's what introduced the bug — users without preferences records cause a NoneType error.

  **Fix attempt A**: Add a null check before unpacking prefs.
  [Called tools: apply_text_patch]

tool (apply_text_patch): Patched /home/computron/webapp/handlers/export_handler.py
  Applied:
  -            prefs = await UserPreferences.get(user_id=user.id)
  -            theme, lang = prefs.theme, prefs.language
  +            prefs = await UserPreferences.get(user_id=user.id)
  +            if prefs is not None:
  +                theme, lang = prefs.theme, prefs.language
  +            else:
  +                theme, lang = "default", "en"

A: Let me run the tests.
  [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ cd /home/computron/webapp && python -m pytest tests/handlers/test_export.py -v
  ============================= test session starts ==============================
  collected 6 items

  tests/handlers/test_export.py::test_export_basic PASSED
  tests/handlers/test_export.py::test_export_with_prefs PASSED
  tests/handlers/test_export.py::test_export_empty_db PASSED
  tests/handlers/test_export.py::test_export_with_prefs_missing FAILED
  tests/handlers/test_export.py::test_export_admin_required PASSED
  tests/handlers/test_export.py::test_export_csv_format PASSED

  FAILURES
  test_export_with_prefs_missing
      AssertionError: Expected CSV to contain "N/A" for missing prefs,
      got "default"

  ========================= 1 failed, 5 passed ============================

A: Fix A partially works — no more 500 error — but `test_export_with_prefs_missing` expects "N/A" as the fallback value, not "default". Let me check the test to see what's expected.
  [Called tools: read_file]

tool (read_file): File: /home/computron/webapp/tests/handlers/test_export.py (lines 45-68)
  45 async def test_export_with_prefs_missing(client, db):
  46     """Users without prefs should show N/A in export."""
  47     user = await User.create(name="Test", email="test@example.com")
  48     # Deliberately don't create UserPreferences
  49     resp = await client.get("/api/users/export?include_prefs=true")
  50     assert resp.status == 200
  51     body = await resp.text()
  52     assert "N/A" in body
  53     lines = body.strip().split("\n")
  54     assert len(lines) == 2  # header + 1 user
  55     data_line = lines[1]
  56     assert "N/A" in data_line

A: The test expects "N/A", not "default". Let me update the fix.

  **Fix attempt B**: Change fallback to "N/A".
  [Called tools: apply_text_patch]

tool (apply_text_patch): Patched /home/computron/webapp/handlers/export_handler.py
  Applied:
  -                theme, lang = "default", "en"
  +                theme, lang = "N/A", "N/A"

A: [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ cd /home/computron/webapp && python -m pytest tests/handlers/test_export.py -v
  ============================= test session starts ==============================
  collected 6 items

  tests/handlers/test_export.py::test_export_basic PASSED
  tests/handlers/test_export.py::test_export_with_prefs PASSED
  tests/handlers/test_export.py::test_export_empty_db PASSED
  tests/handlers/test_export.py::test_export_with_prefs_missing PASSED
  tests/handlers/test_export.py::test_export_admin_required PASSED
  tests/handlers/test_export.py::test_export_csv_format FAILED

  FAILURES
  test_export_csv_format
      AssertionError: CSV header mismatch.
      Expected: "Name,Email,Created,Theme,Language,Timezone"
      Got: "Name,Email,Created,Theme,Language"

  ========================= 1 failed, 5 passed ============================

A: A different test failed now. The CSV format test expects a "Timezone" column that doesn't exist in the code. This must be another part of the `a3f8c21` commit that was incomplete — the test was updated to expect a Timezone column but the handler wasn't updated to include it. Let me check the model.
  [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ cd /home/computron/webapp && python -c "from webapp.models import UserPreferences; print([f.name for f in UserPreferences._meta.fields])"
  ['id', 'user_id', 'theme', 'language', 'timezone', 'notifications_enabled']

A: The `UserPreferences` model has a `timezone` field but the export handler doesn't include it. The test was updated to expect it but the handler code wasn't.

  **Fix C**: Add timezone to the export and fix the None handling to include it.
  [Called tools: apply_text_patch]

tool (apply_text_patch): Patched /home/computron/webapp/handlers/export_handler.py
  Applied:
  -            prefs = await UserPreferences.get(user_id=user.id)
  -            if prefs is not None:
  -                theme, lang = prefs.theme, prefs.language
  -            else:
  -                theme, lang = "N/A", "N/A"
  -            rows.append([name, email, created, theme, lang])
  +            prefs = await UserPreferences.get(user_id=user.id)
  +            if prefs is not None:
  +                theme, lang, tz = prefs.theme, prefs.language, prefs.timezone
  +            else:
  +                theme, lang, tz = "N/A", "N/A", "N/A"
  +            rows.append([name, email, created, theme, lang, tz])

A: Also need to update the header row.
  [Called tools: apply_text_patch]

tool (apply_text_patch): Patched /home/computron/webapp/handlers/export_handler.py
  Applied:
  -    writer.writerow(["Name", "Email", "Created"] +
  -                    (["Theme", "Language"] if include_prefs else []))
  +    writer.writerow(["Name", "Email", "Created"] +
  +                    (["Theme", "Language", "Timezone"] if include_prefs else []))

A: [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ cd /home/computron/webapp && python -m pytest tests/handlers/test_export.py -v
  ============================= test session starts ==============================
  collected 6 items

  tests/handlers/test_export.py::test_export_basic PASSED
  tests/handlers/test_export.py::test_export_with_prefs PASSED
  tests/handlers/test_export.py::test_export_empty_db PASSED
  tests/handlers/test_export.py::test_export_with_prefs_missing PASSED
  tests/handlers/test_export.py::test_export_admin_required PASSED
  tests/handlers/test_export.py::test_export_csv_format PASSED

  ========================= 6 passed ============================

A: All 6 tests pass. Here's a summary of the fix:

  **Root cause**: Commit `a3f8c21` added `include_prefs` to the export endpoint but:
  1. Didn't handle users without a UserPreferences record (caused NoneType error)
  2. Didn't include the `timezone` field that the test expected

  **Changes to `export_handler.py`**:
  - Added null check for `UserPreferences.get()` returning None
  - Used "N/A" as fallback for missing preferences (matching test expectations)
  - Added `timezone` field to both the data rows and CSV header

  **File modified**: `/home/computron/webapp/handlers/export_handler.py` (lines 21-23, 29-30)

user: Thanks. Can you also run the full test suite to make sure nothing else broke?
```

## Compaction Boundary Analysis

With `keep_recent=6`:
- **Total messages**: 1 system + ~24 non-system
- **Pinned**: First user message (error report with traceback location)
- **Compacted**: Messages 2 through ~18 (code reading, git log, fix A, test fail, fix B, test fail, fix C, header fix)
- **Kept**: Last 6 non-system messages (likely the final test run, summary, and user's follow-up about full test suite)

### What crosses the compaction boundary

The user asked to run the full test suite. The agent needs to know:
- The project path (`/home/computron/webapp`)
- What file was modified (`export_handler.py`)
- That all 6 export tests now pass (so if the full suite fails, it's a different issue)
- The complete fix (null check + N/A fallback + timezone column) — in case a full suite failure relates to these changes
- That Fix A used "default" (wrong) and Fix B didn't have timezone (incomplete) — if tests fail again, the agent shouldn't regress to these partial fixes

### Critical: failed approaches

Fix A and Fix B are the most important things the summary must preserve:
- **Fix A failed because**: used "default"/"en" as fallback values, but tests expect "N/A"
- **Fix B failed because**: missing timezone column that the test expected in CSV header

If these are dropped as "process narration," the agent has no way to know WHY the current fix looks the way it does, and might try simpler approaches if a new test failure appears.

## Required Facts

| Fact | Anchored pattern |
|------|-----------------|
| File modified: export_handler.py | `r"export_handler\.py"` |
| Bug: NoneType error on line 21-23 | `r"None\s*[Tt]ype|None.*unpack|prefs.*None|null.*prefs|no.*preferences"` |
| Commit that introduced bug: a3f8c21 | `r"a3f8c21"` |
| include_prefs query param | `r"include_prefs"` |
| Fix A tried: "default"/"en" fallback | `r"default.*fallback|\"default\"|fallback.*default|used.*default"` |
| Fix A failed: test expected "N/A" not "default" | `r"N/A.*not.*default|expected.*N/A|\"default\".*wrong|default.*incorrect|should.*N/A"` |
| Fix B tried: changed to "N/A" | `r"N/A"` |
| Fix B failed: missing timezone column | `r"[Tt]imezone.*missing|missing.*[Tt]imezone|[Tt]imezone.*column|no.*[Tt]imezone|without.*[Tt]imezone"` |
| Fix C: added timezone + N/A fallback | `r"[Tt]imezone"` |
| All 6 tests pass | `r"6\s*pass|all.*pass|tests?\s*pass"` |
| UserPreferences model has timezone field | `r"timezone\s*field|UserPreferences.*timezone|model.*timezone"` |
| Project path | `r"/home/computron/webapp"` |



## Probes

| Question | Pass pattern | Fail pattern |
|----------|-------------|-------------|
| What should you do next? | `r"full.*test|test.*suite|pytest"` | `r"read.*file|look.*code|investigate"` |
| What fixes were tried that didn't work and why? | `r"default|timezone"` | — |
| What file was modified? | `r"export_handler"` | — |
