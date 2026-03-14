"""Integration test: SummarizeStrategy across diverse agent scenarios.

Tests that the summarizer correctly distills key facts from different types
of agent sessions while discarding bulky intermediate tool outputs.

Run with:
    PYTHONPATH=. uv run pytest tests/agents/ollama/sdk/context/test_summarize_scenarios.py -v -s
"""

import time

import pytest

from sdk.context import ContextStats, ConversationHistory, SummarizeStrategy

_MODEL = "qwen2.5:3b"


# ---------------------------------------------------------------------------
# Scenario 1: Multi-step code debugging
#
# SHOULD FORGET: file contents, grep output, wrong-file detour, error tracebacks
# SHOULD REMEMBER: the bug (race condition), the file (worker.py:142),
#                   the fix (asyncio.Lock), that tests now pass
# ---------------------------------------------------------------------------

def _build_debugging_history() -> ConversationHistory:
    """Simulate a coding agent debugging a race condition."""
    return ConversationHistory([
        {"role": "system", "content": "You are a coding assistant with file and terminal tools."},
        # User reports the bug
        {"role": "user", "content": (
            "My worker pool keeps producing wrong counts. The total should be 1000 "
            "but I keep getting random numbers like 987 or 993. The code is in "
            "/home/user/project/src/worker.py."
        )},
        # Assistant reads the file
        {
            "role": "assistant",
            "content": "Let me look at the worker code.",
            "tool_calls": [
                {"function": {"name": "read_file", "arguments": {"path": "/home/user/project/src/worker.py"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "read_file",
            "content": (
                "import asyncio\n\n"
                "class WorkerPool:\n"
                "    def __init__(self, num_workers: int = 10):\n"
                "        self.num_workers = num_workers\n"
                "        self.counter = 0\n"
                "        self.results = []\n\n"
                "    async def process_item(self, item):\n"
                "        await asyncio.sleep(0.01)  # simulate work\n"
                "        self.counter += 1  # line 142\n"
                "        self.results.append(item)\n\n"
                "    async def run(self, items):\n"
                "        tasks = []\n"
                "        for item in items:\n"
                "            task = asyncio.create_task(self.process_item(item))\n"
                "            tasks.append(task)\n"
                "        await asyncio.gather(*tasks)\n"
                "        return self.counter\n"
            ),
        },
        # Assistant first checks the wrong file
        {
            "role": "assistant",
            "content": "Let me also check the test file to see how it's called.",
            "tool_calls": [
                {"function": {"name": "read_file", "arguments": {"path": "/home/user/project/tests/test_worker.py"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "read_file",
            "content": (
                "import pytest\n"
                "from src.worker import WorkerPool\n\n"
                "class TestWorkerPool:\n"
                "    @pytest.mark.asyncio\n"
                "    async def test_count(self):\n"
                "        pool = WorkerPool(num_workers=10)\n"
                "        items = list(range(1000))\n"
                "        count = await pool.run(items)\n"
                "        assert count == 1000  # This fails intermittently!\n\n"
                "    @pytest.mark.asyncio\n"
                "    async def test_results_complete(self):\n"
                "        pool = WorkerPool(num_workers=5)\n"
                "        items = list(range(100))\n"
                "        await pool.run(items)\n"
                "        assert len(pool.results) == 100\n"
            ),
        },
        # Assistant runs the test to reproduce
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "run_command", "arguments": {"command": "cd /home/user/project && python -m pytest tests/test_worker.py -v"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "run_command",
            "content": (
                "============================= test session starts ==============================\n"
                "collected 2 items\n\n"
                "tests/test_worker.py::TestWorkerPool::test_count FAILED\n"
                "tests/test_worker.py::TestWorkerPool::test_results_complete PASSED\n\n"
                "FAILURES\n"
                "tests/test_worker.py::TestWorkerPool::test_count\n"
                "    AssertionError: assert 994 == 1000\n\n"
                "========================= 1 failed, 1 passed ============================\n"
            ),
        },
        # Assistant diagnoses and explains
        {
            "role": "assistant",
            "content": (
                "I found the bug. It's a classic race condition on line 142 of worker.py. "
                "The line `self.counter += 1` is not atomic — when multiple coroutines "
                "run concurrently via `asyncio.gather`, they can read the same value of "
                "`self.counter` before any of them writes back the incremented value.\n\n"
                "The fix is to protect the counter with an `asyncio.Lock`. Let me apply it."
            ),
            "tool_calls": [
                {"function": {"name": "edit_file", "arguments": {
                    "path": "/home/user/project/src/worker.py",
                    "changes": "Add asyncio.Lock to protect self.counter",
                }}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "edit_file",
            "content": "File updated successfully: /home/user/project/src/worker.py",
        },
        # Verify the fix
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "run_command", "arguments": {"command": "cd /home/user/project && python -m pytest tests/test_worker.py -v --count=5"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "run_command",
            "content": (
                "============================= test session starts ==============================\n"
                "collected 10 items\n\n"
                "tests/test_worker.py::TestWorkerPool::test_count[1-5] PASSED\n"
                "tests/test_worker.py::TestWorkerPool::test_results_complete[1-5] PASSED\n\n"
                "========================= 10 passed ============================\n"
            ),
        },
        # Final summary from assistant
        {
            "role": "assistant",
            "content": (
                "The bug is fixed. The race condition on `self.counter += 1` at line 142 "
                "of `/home/user/project/src/worker.py` was caused by concurrent coroutines "
                "reading stale values. I added an `asyncio.Lock` to serialize access to the "
                "counter. All tests now pass consistently across 5 runs."
            ),
        },
        # User follow-up
        {"role": "user", "content": "Could the results list have the same issue?"},
        {
            "role": "assistant",
            "content": (
                "Good question. `list.append()` in CPython is actually thread-safe due to "
                "the GIL, and in asyncio it's safe because `append` completes in a single "
                "bytecode operation. However, if you ever need to read `len(self.results)` "
                "while tasks are still running, you could get stale reads. For safety, I'd "
                "recommend protecting it with the same lock."
            ),
        },
    ])

_DEBUGGING_FACTS = [
    ("race condition", lambda t: "race" in t or "concurrent" in t),
    ("worker.py file", lambda t: "worker" in t),
    ("asyncio.Lock fix", lambda t: "lock" in t),
    ("counter bug", lambda t: "counter" in t or "count" in t),
]


# ---------------------------------------------------------------------------
# Scenario 2: Research with dead ends
#
# SHOULD FORGET: page snapshots from irrelevant sites, navigation noise,
#                404 error page, the WordPress blog that wasn't useful
# SHOULD REMEMBER: React vs Vue comparison, specific stats/findings,
#                   user preference for React
# ---------------------------------------------------------------------------

def _build_research_history() -> ConversationHistory:
    """Simulate a browser agent researching frameworks with dead ends."""
    return ConversationHistory([
        {"role": "system", "content": "You are a helpful AI assistant with browser tools."},
        {"role": "user", "content": "I need to choose between React and Vue for a new project. Help me compare them."},
        # Dead end 1: 404 page
        {
            "role": "assistant",
            "content": "I'll research the latest comparisons for you.",
            "tool_calls": [
                {"function": {"name": "browse_page", "arguments": {"url": "https://stateofjs.com/2025/frameworks"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "browse_page",
            "content": (
                "[Page: 404 Not Found | https://stateofjs.com/2025/frameworks | 404]\n"
                "[Viewport: 0-500 of 500px]\n\n"
                "[h1] Page Not Found\n"
                "The page you're looking for doesn't exist.\n"
                "[1] [link] Go to homepage\n"
            ),
        },
        # Dead end 2: irrelevant blog
        {
            "role": "assistant",
            "content": "That page doesn't exist. Let me try another source.",
            "tool_calls": [
                {"function": {"name": "browse_page", "arguments": {"url": "https://blog.example.com/react-vs-vue-2025"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "browse_page",
            "content": (
                "[Page: React vs Vue in 2025 | https://blog.example.com/react-vs-vue-2025 | 200]\n"
                "[Viewport: 0-900 of 3000px]\n\n"
                "[h1] React vs Vue: My Personal Blog Post\n"
                "By John Smith · January 2025\n"
                "I've been using WordPress for 10 years and decided to try modern frameworks.\n"
                "After watching a YouTube video, I think React is neat.\n"
                "[h2] My First React App\n"
                "I made a todo list! It was fun but confusing.\n"
                "[h2] My First Vue App\n"
                "Vue was easier to understand.\n"
                "[h2] Conclusion\n"
                "Both are good. Use what you like!\n"
                "[2] [link] Subscribe to my newsletter\n"
            ),
        },
        # Useful source: actual data
        {
            "role": "assistant",
            "content": "That wasn't very useful. Let me find something with actual data.",
            "tool_calls": [
                {"function": {"name": "browse_page", "arguments": {"url": "https://survey.stackoverflow.com/2025/technology"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "browse_page",
            "content": (
                "[Page: Stack Overflow Developer Survey 2025 | https://survey.stackoverflow.com/2025 | 200]\n"
                "[Viewport: 0-900 of 8000px]\n\n"
                "[h1] Most Popular Web Frameworks\n"
                "[h2] Usage Statistics\n"
                "React: 58.3% of respondents\n"
                "Vue.js: 23.1% of respondents\n"
                "Angular: 17.8% of respondents\n"
                "Svelte: 12.4% of respondents\n"
                "[h2] Satisfaction Ratings\n"
                "React: 72% satisfied\n"
                "Vue.js: 78% satisfied\n"
                "Svelte: 89% satisfied\n"
                "Angular: 51% satisfied\n"
                "[h2] Learning Curve\n"
                "Easiest to learn: Vue.js (82% agree)\n"
                "Most career opportunities: React (91% agree)\n"
                "[3] [link] Full methodology\n"
            ),
        },
        # Another useful source
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "browse_page", "arguments": {"url": "https://npmtrends.com/react-vs-vue"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "browse_page",
            "content": (
                "[Page: npm trends: react vs vue | https://npmtrends.com/react-vs-vue | 200]\n"
                "[Viewport: 0-900 of 2000px]\n\n"
                "[h1] react vs vue\n"
                "Weekly Downloads (last 6 months):\n"
                "react: 28.5M/week\n"
                "vue: 5.2M/week\n"
                "GitHub Stars:\n"
                "react: 228k\n"
                "vue: 210k\n"
            ),
        },
        # Assistant synthesizes findings
        {
            "role": "assistant",
            "content": (
                "Here's my comparison based on current data:\n\n"
                "**React**:\n"
                "- 58.3% market share (Stack Overflow 2025)\n"
                "- 28.5M weekly npm downloads\n"
                "- 72% developer satisfaction\n"
                "- 91% say most career opportunities\n"
                "- Steeper learning curve\n"
                "- Backed by Meta\n\n"
                "**Vue**:\n"
                "- 23.1% market share\n"
                "- 5.2M weekly npm downloads\n"
                "- 78% developer satisfaction (higher than React!)\n"
                "- 82% say easiest to learn\n"
                "- Growing but smaller ecosystem\n"
                "- Community-driven (Evan You)\n\n"
                "**My recommendation**: If career opportunities and ecosystem are priorities, "
                "go with React. If developer experience and simplicity matter more, Vue is excellent."
            ),
        },
        # User states preference
        {"role": "user", "content": "I think React makes more sense for hiring. But is the learning curve really that bad?"},
        {
            "role": "assistant",
            "content": (
                "The learning curve concern is real but manageable. React itself is a small "
                "library — the complexity comes from the ecosystem choices (state management, "
                "routing, build tools). With Next.js, most of those decisions are made for you.\n\n"
                "For a team of 3-5 developers, I'd estimate 2-3 weeks to get productive with "
                "React if they know JavaScript well. Vue might be 1-2 weeks."
            ),
        },
    ])

_RESEARCH_FACTS = [
    ("React vs Vue topic", lambda t: "react" in t and "vue" in t),
    ("React market share ~58%", lambda t: "58" in t or "market share" in t or "popular" in t),
    ("Vue higher satisfaction", lambda t: "satisfaction" in t or "easier" in t or "simpler" in t),
    ("user leaning React for hiring", lambda t: "hiring" in t or "career" in t),
]


# ---------------------------------------------------------------------------
# Scenario 3: File reorganization with many small operations
#
# SHOULD FORGET: individual ls/mkdir/mv tool outputs, directory listings,
#                intermediate file states
# SHOULD REMEMBER: new structure (src/, tests/, docs/), 15 files moved,
#                   imports updated, user wants tests at root level
# ---------------------------------------------------------------------------

def _build_file_reorg_history() -> ConversationHistory:
    """Simulate a coding agent reorganizing a flat project structure."""
    return ConversationHistory([
        {"role": "system", "content": "You are a coding assistant with file and terminal tools."},
        {"role": "user", "content": (
            "This project has all Python files in the root. Can you reorganize it into "
            "src/, tests/, and docs/ folders? Keep tests in a root-level tests/ directory, "
            "NOT inside src/."
        )},
        # List files
        {
            "role": "assistant",
            "content": "Let me see what we're working with.",
            "tool_calls": [
                {"function": {"name": "run_command", "arguments": {"command": "ls -la /home/user/myproject/"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "run_command",
            "content": (
                "total 128\n"
                "drwxr-xr-x  2 user user  4096 Jan 15 10:00 .\n"
                "-rw-r--r--  1 user user  1200 Jan 15 09:50 app.py\n"
                "-rw-r--r--  1 user user   800 Jan 15 09:50 config.py\n"
                "-rw-r--r--  1 user user  2400 Jan 15 09:50 database.py\n"
                "-rw-r--r--  1 user user  1600 Jan 15 09:50 models.py\n"
                "-rw-r--r--  1 user user  3200 Jan 15 09:50 routes.py\n"
                "-rw-r--r--  1 user user   950 Jan 15 09:50 utils.py\n"
                "-rw-r--r--  1 user user  1100 Jan 15 09:50 middleware.py\n"
                "-rw-r--r--  1 user user  1800 Jan 15 09:50 auth.py\n"
                "-rw-r--r--  1 user user  2100 Jan 15 09:50 cache.py\n"
                "-rw-r--r--  1 user user   700 Jan 15 09:50 logger.py\n"
                "-rw-r--r--  1 user user  1500 Jan 15 09:50 validators.py\n"
                "-rw-r--r--  1 user user  1900 Jan 15 09:50 serializers.py\n"
                "-rw-r--r--  1 user user   600 Jan 15 09:50 constants.py\n"
                "-rw-r--r--  1 user user  2800 Jan 15 09:50 tasks.py\n"
                "-rw-r--r--  1 user user  1400 Jan 15 09:50 workers.py\n"
                "-rw-r--r--  1 user user   500 Jan 15 09:50 test_app.py\n"
                "-rw-r--r--  1 user user   800 Jan 15 09:50 test_database.py\n"
                "-rw-r--r--  1 user user   600 Jan 15 09:50 test_auth.py\n"
                "-rw-r--r--  1 user user   700 Jan 15 09:50 test_routes.py\n"
                "-rw-r--r--  1 user user   300 Jan 15 09:50 README.md\n"
                "-rw-r--r--  1 user user   200 Jan 15 09:50 setup.py\n"
            ),
        },
        # Create directories
        {
            "role": "assistant",
            "content": "I see 15 source files and 4 test files. Let me create the new structure.",
            "tool_calls": [
                {"function": {"name": "run_command", "arguments": {"command": "mkdir -p /home/user/myproject/{src,tests,docs}"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "run_command",
            "content": "",
        },
        # Move source files (batch 1)
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "run_command", "arguments": {
                    "command": "cd /home/user/myproject && mv app.py config.py database.py models.py routes.py utils.py middleware.py auth.py src/"
                }}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "run_command",
            "content": "",
        },
        # Move source files (batch 2)
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "run_command", "arguments": {
                    "command": "cd /home/user/myproject && mv cache.py logger.py validators.py serializers.py constants.py tasks.py workers.py src/"
                }}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "run_command",
            "content": "",
        },
        # Move test files
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "run_command", "arguments": {
                    "command": "cd /home/user/myproject && mv test_*.py tests/"
                }}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "run_command",
            "content": "",
        },
        # Create __init__.py
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "run_command", "arguments": {
                    "command": "touch /home/user/myproject/src/__init__.py /home/user/myproject/tests/__init__.py"
                }}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "run_command",
            "content": "",
        },
        # Update imports across all files
        {
            "role": "assistant",
            "content": "Now I need to update all the import paths since files moved into src/.",
            "tool_calls": [
                {"function": {"name": "run_command", "arguments": {
                    "command": "cd /home/user/myproject && grep -rl 'from database' src/ | head -5"
                }}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "run_command",
            "content": (
                "src/app.py\n"
                "src/routes.py\n"
                "src/models.py\n"
            ),
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "run_command", "arguments": {
                    "command": (
                        "cd /home/user/myproject && "
                        "find src/ -name '*.py' -exec sed -i 's/from database/from src.database/g' {} + && "
                        "find src/ -name '*.py' -exec sed -i 's/from models/from src.models/g' {} + && "
                        "find src/ -name '*.py' -exec sed -i 's/from utils/from src.utils/g' {} + && "
                        "find src/ -name '*.py' -exec sed -i 's/from config/from src.config/g' {} + && "
                        "find src/ -name '*.py' -exec sed -i 's/from auth/from src.auth/g' {} + && "
                        "find tests/ -name '*.py' -exec sed -i 's/from app/from src.app/g' {} + && "
                        "find tests/ -name '*.py' -exec sed -i 's/from database/from src.database/g' {} + && "
                        "find tests/ -name '*.py' -exec sed -i 's/from auth/from src.auth/g' {} + && "
                        "find tests/ -name '*.py' -exec sed -i 's/from routes/from src.routes/g' {} +"
                    )
                }}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "run_command",
            "content": "",
        },
        # Verify
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"function": {"name": "run_command", "arguments": {"command": "cd /home/user/myproject && python -m pytest tests/ -v"}}},
            ],
        },
        {
            "role": "tool",
            "tool_name": "run_command",
            "content": (
                "============================= test session starts ==============================\n"
                "collected 12 items\n\n"
                "tests/test_app.py::test_startup PASSED\n"
                "tests/test_app.py::test_shutdown PASSED\n"
                "tests/test_database.py::test_connection PASSED\n"
                "tests/test_database.py::test_query PASSED\n"
                "tests/test_auth.py::test_login PASSED\n"
                "tests/test_auth.py::test_token PASSED\n"
                "tests/test_routes.py::test_index PASSED\n"
                "tests/test_routes.py::test_api_users PASSED\n"
                "tests/test_routes.py::test_api_items PASSED\n"
                "tests/test_routes.py::test_404 PASSED\n"
                "tests/test_routes.py::test_auth_required PASSED\n"
                "tests/test_routes.py::test_cors PASSED\n\n"
                "========================= 12 passed ============================\n"
            ),
        },
        {
            "role": "assistant",
            "content": (
                "Done! Here's the new project structure:\n\n"
                "```\n"
                "myproject/\n"
                "  src/           # 15 source files\n"
                "    __init__.py\n"
                "    app.py\n"
                "    config.py\n"
                "    database.py\n"
                "    models.py\n"
                "    routes.py\n"
                "    ... (10 more)\n"
                "  tests/         # 4 test files (root level, not inside src/)\n"
                "    __init__.py\n"
                "    test_app.py\n"
                "    test_database.py\n"
                "    test_auth.py\n"
                "    test_routes.py\n"
                "  docs/\n"
                "  README.md\n"
                "  setup.py\n"
                "```\n\n"
                "All import paths have been updated from `from module` to `from src.module`. "
                "All 12 tests pass."
            ),
        },
        {"role": "user", "content": "Perfect. Can you also move README.md into docs/?"},
        {
            "role": "assistant",
            "content": (
                "I'd recommend keeping README.md in the project root — that's the standard "
                "convention and GitHub/PyPI expect it there. I can create a docs/ folder with "
                "more detailed documentation that links to the README if you'd like."
            ),
        },
    ])

_FILE_REORG_FACTS = [
    ("src/ directory", lambda t: "src/" in t or "src " in t or "src directory" in t),
    ("tests at root level", lambda t: "tests" in t and ("root" in t or "not inside" in t or "not under" in t or "top" in t or "separate" in t)),
    ("15 files moved", lambda t: "15" in t or "fifteen" in t),
    ("imports updated", lambda t: "import" in t),
]


# ---------------------------------------------------------------------------
# Test runner — parameterized across scenarios
# ---------------------------------------------------------------------------

_SCENARIOS = [
    ("debugging", _build_debugging_history, _DEBUGGING_FACTS),
    ("research", _build_research_history, _RESEARCH_FACTS),
    ("file_reorg", _build_file_reorg_history, _FILE_REORG_FACTS),
]


@pytest.mark.integration
@pytest.mark.parametrize(
    "scenario_name, build_fn, expected_facts",
    _SCENARIOS,
    ids=[s[0] for s in _SCENARIOS],
)
async def test_summarize_scenario(scenario_name, build_fn, expected_facts):
    """Test that key facts survive summarization across different scenarios."""
    strategy = SummarizeStrategy(
        threshold=0.75,
        keep_recent=2,  # keep only last user + assistant exchange
        summary_model=_MODEL,
    )
    history = build_fn()
    original_len = len(history)
    stats = ContextStats(context_used=96000, context_limit=128000)

    assert strategy.should_apply(history, stats)

    start = time.perf_counter()
    await strategy.apply(history, stats)
    elapsed = time.perf_counter() - start

    # Verify structure — first user message is pinned, summary follows it
    assert history.system_message is not None
    # Find the summary message (has the compaction prefix)
    summary_msg = None
    for msg in history.messages:
        if (msg.get("role") == "user"
                and msg.get("content", "").startswith("[Conversation summary")):
            summary_msg = msg
            break
    assert summary_msg is not None, "No summary message found in history"

    summary_text = summary_msg["content"].lower()

    print(f"\n{'=' * 70}")
    print(f"Scenario: {scenario_name} | Model: {_MODEL}")
    print(f"Time: {elapsed:.2f}s | {original_len} → {len(history)} messages")
    print(f"Summary: {len(summary_msg['content'])} chars")
    print(f"{'=' * 70}")
    print(summary_msg["content"])
    print(f"{'=' * 70}")

    facts_found = 0
    for desc, check_fn in expected_facts:
        found = check_fn(summary_text)
        facts_found += int(found)
        print(f"  {'✓' if found else '✗'} {desc}")

    print(f"Key facts: {facts_found}/{len(expected_facts)}")

    assert facts_found >= len(expected_facts) // 2, (
        f"Scenario '{scenario_name}': only {facts_found}/{len(expected_facts)} key facts preserved. "
        f"Summary: {summary_msg['content'][:300]}..."
    )
