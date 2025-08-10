# Coder workflow improvements

This proposal tightens the workflow to reliably take a natural-language assignment, plan it, implement it, and verify it using only unit/integration tests inside the virtual computer (VC). It also adds guardrails so the VC never hangs on long-lived commands.

## Hard constraints
- VC has no window system; never start servers or GUI apps.
- Only run short-lived commands; anything that watches/serves/blocks is forbidden.
- Prefer tests and static checks for verification; do not “open” or “view” apps.
- All work happens under a per-run workspace folder mounted into the VC.

## Orchestration: state machine
Phases executed sequentially with retries and budgets:
1) Requirements extraction (NEW) → structured scope/acceptance criteria.
2) System design (existing) → architecture doc.
3) Planning (existing, stricter) → JSON plan steps (schema below).
4) Scaffold & env setup (NEW) → venv/node setup, deps, project skeleton.
5) Test design first (NEW) → write failing unit/integration tests per step.
6) Implementation per step (existing coder_dev) → code changes only.
7) Verification (NEW) → run pytest and static checks; parse results.
8) Review/gate (improved) → accept only if tests pass and checks clean.
9) Fix loop (NEW) → patch until green or budget/time exhausted.

Artifacts saved in the workspace: DESIGN.md, PLAN.json, REQUIREMENTS.json, TEST_REPORT.json, LINT_REPORT.json, COVERAGE (if enabled), CHANGELOG.md.

## New/updated agents
- RequirementsAgent (NEW)
  - Input: assignment text
  - Output (JSON): goals, non-goals, constraints (runtime, tooling), acceptance criteria, risks.
  - Guardrails: keep ambiguous areas as explicit questions for Planner.

- SystemDesignerAgent (existing, prompt update)
  - Add: languages, libs, dir layout, test strategy, static checks, headless-only constraint.

- PlannerAgent (existing, strict JSON)
  - Returns only JSON array of steps conforming to PlanStep schema.
  - No code in plan; may include bash commands but must be test-only and short-lived.

- ScaffolderAgent (NEW)
  - Creates venv (Python) and/or initializes Node workspace if needed.
  - Installs test/dev deps locally inside the workspace.
  - Generates minimal project skeleton and config (pyproject.toml, pytest.ini if missing).

- TestDesignerAgent (NEW)
  - Writes failing tests first for each step based on acceptance criteria.
  - Python: pytest tests under tests/ matching repo style; Node (if used): headless-only tests.

- CoderDevAgent (existing, prompt update)
  - Implements code to satisfy tests; edits only relevant files; updates tests when refactors.
  - Always runs tests after changes via the VerifierAgent.

- VerifierAgent (NEW)
  - Runs: pytest (unit/integration subsets), optional ruff/mypy; returns parsed JSON results.
  - No servers; uses quiet flags and timeouts.

- ReviewerAgent (existing, output contract update)
  - Returns JSON: { decision: accepted|rejected, reasons: [], must_fixes: [], nice_to_haves: [] }.
  - Must check VerifierAgent results; cannot accept if tests fail.

- FixerAgent (NEW)
  - Consumes failing test traces and lints; proposes minimal diffs; writes patches.

## Planner output schema (strict)
All planner outputs MUST be valid JSON conforming to this shape. Types are illustrative; enforce via Pydantic in the orchestrator.

```json
[
  {
    "id": "step-1",
    "title": "Create project skeleton",
    "instructions": "Create initial package structure and config files.",
    "files": [
      { "path": "pyproject.toml", "purpose": "project metadata & deps" },
      { "path": "src/pkg/__init__.py", "purpose": "package init" }
    ],
    "commands": [
      { "run": "python -m venv .venv && . .venv/bin/activate && pip install -e .[test]", "timeout_sec": 180 }
    ],
    "tests": [
      { "path": "tests/test_basic.py", "description": "sanity test" }
    ],
    "acceptance": [
      "pytest passes for tests/test_basic.py"
    ]
  }
]
```

Recommended additional fields:
- depends_on: ["step-0"]
- retries: 2
- when: condition string (optional)

## Typed orchestration surface
Extend StepYield with structured signals:
- step_id, title
- started_at, finished_at
- completed (bool)
- artifacts: [relative paths]
- verification: { tests_passed: bool, failed: int, passed: int, mypy_ok: bool, ruff_ok: bool }
- logs: [truncated strings]
- error: optional message

Enforce via Pydantic models; forbid Any; map to UI updates.

## Guardrails in the VC
- Allowlist commands for run_bash_cmd: pytest, python -m pip, python -m venv, ruff, mypy, node/npm (install, test), git (init/add/commit) optional.
- Denylist: serve, dev, start, watch, tail -f, sleep infinity, http.server, playwright headed.
- Add per-command timeout overrides: installs/tests up to 180s; default 60s.
- Always run with `set -euo pipefail` and ensure commands are one-shot.

## Prompt improvements (high level)
- CoderDevAgent: “Never start servers or watchers. Only run unit/integration tests. If you need to validate behavior, encode it as a test. Use read_file_directory to confirm files before editing. Keep changes minimal and focused per step.”
- PlannerAgent: “Return only valid JSON matching the schema; include file paths (relative), commands that are short-lived, and tests to create. Do not include code.”
- ReviewerAgent: “Return strict JSON; accept only if VerifierAgent reports green.”
- VerifierAgent: “Run pytest with -q, capture JSON (pytest-json-report) if installed; include summary and first failing trace.”

## Minimal changes to existing code to adopt
1) Add Pydantic models for PlanStep and StepResult (strict fields, enums for commands).
2) Replace free-form reviewer output parsing with strict JSON.
3) Insert VerifierAgent after each implementation step; block advancement on red.
4) Save PLAN.json and DESIGN.md in the workspace; persist reports.
5) Add allowlist/denylist and per-command timeouts in run_bash_cmd.

## Suggested tests to add
- test_planner_parsing_strict_json: invalid shape rejected; valid shape accepted.
- test_verifier_reports_failures: create a failing test and assert parsed failure.
- test_allowlist_blocks_long_running: `python -m http.server` rejected.
- test_fix_loop_turns_red_to_green: failing test → FixerAgent patch → green.

## Notes on web assignments (e.g., HTML/CSS/JS game)
- No browsers/GUI; validate with:
  - Static checks (eslint-like) and Node unit tests using jsdom (headless) if Node is permitted.
  - Deterministic functions extracted from game logic with pure unit tests.
  - Do not attempt to “run” a server; encode behavior as tests.

## Next steps
- Implement VerifierAgent + strict reviewer JSON.
- Add allowlist/denylist and timeouts to run_bash_cmd.
- Introduce PlanStep Pydantic schema and enforce throughout.
- Update agent prompts and wire new agents into coder_agent_workflow.
