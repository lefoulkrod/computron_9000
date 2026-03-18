# Scenario 10: User Redirect Mid-Task

## Purpose

Tests what happens when the user abandons the current approach and redirects the agent to something completely different mid-task. The summarizer needs to capture both the abandoned work (so the agent doesn't go back to it) AND the new direction.

## Conversation

Agent starts building a REST API in Flask, user pivots to FastAPI instead, then further pivots from SQLite to PostgreSQL.

```
system: You are a coding assistant with file and terminal tools.

user: Build me a simple REST API for a todo list app. Use Flask and SQLite.

A: I'll set up a Flask API with SQLite. Let me create the project structure.
  [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ mkdir -p /home/computron/todo_api && cd /home/computron/todo_api && pip install flask
  Successfully installed flask-3.0.0

A: [Called tools: write_file]

tool (write_file): Created /home/computron/todo_api/app.py (Flask API with SQLite, CRUD endpoints)

A: [Called tools: write_file]

tool (write_file): Created /home/computron/todo_api/models.py (SQLite schema with todos table)

A: [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ cd /home/computron/todo_api && python -c "from models import init_db; init_db()"
  Database initialized: todo.db

A: [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ cd /home/computron/todo_api && python app.py &
  * Running on http://127.0.0.1:5000

A: [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ curl -s -X POST http://127.0.0.1:5000/todos -H "Content-Type: application/json" -d '{"title": "Test todo", "done": false}' | python -m json.tool
  {
    "id": 1,
    "title": "Test todo",
    "done": false,
    "created_at": "2025-03-17T10:00:00"
  }

A: Flask API is working. I've created:
  - `/home/computron/todo_api/app.py` — Flask API with CRUD endpoints (GET, POST, PUT, DELETE /todos)
  - `/home/computron/todo_api/models.py` — SQLite models
  - `/home/computron/todo_api/todo.db` — SQLite database
  - API running on http://127.0.0.1:5000

user: Actually, let's use FastAPI instead of Flask. It has better async support and auto-generates docs.

A: Good call. Let me rebuild with FastAPI. I'll stop the Flask server first.
  [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ pkill -f "python app.py" && pip install fastapi uvicorn
  Successfully installed fastapi-0.110.0 uvicorn-0.29.0

A: [Called tools: write_file]

tool (write_file): Created /home/computron/todo_api/app.py (FastAPI version, overwrote Flask version)

A: [Called tools: write_file]

tool (write_file): Created /home/computron/todo_api/models.py (Updated for SQLAlchemy async with SQLite)

A: [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ cd /home/computron/todo_api && uvicorn app:app --host 0.0.0.0 --port 5000 &
  INFO:     Uvicorn running on http://0.0.0.0:5000

A: [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ curl -s http://127.0.0.1:5000/docs | head -5
  <!DOCTYPE html>
  <html>
  <head><title>FastAPI - Swagger UI</title></head>

A: FastAPI version is running with auto-generated docs at http://127.0.0.1:5000/docs. Files updated in place — same paths as before.

user: Actually one more thing — let's use PostgreSQL instead of SQLite. I want this to be production-ready.

A: Good idea. Let me update the database layer.
  [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ pip install asyncpg sqlalchemy[asyncio]
  Successfully installed asyncpg-0.29.0

A: [Called tools: write_file]

tool (write_file): Updated /home/computron/todo_api/models.py (PostgreSQL with asyncpg, connection string from env var)

A: [Called tools: write_file]

tool (write_file): Created /home/computron/todo_api/.env (DATABASE_URL=postgresql+asyncpg://computron:password@localhost:5432/todo_db)

A: [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ cd /home/computron/todo_api && createdb todo_db && python -c "from models import init_db; import asyncio; asyncio.run(init_db())"
  Database 'todo_db' created and tables initialized.

A: [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ cd /home/computron/todo_api && uvicorn app:app --host 0.0.0.0 --port 5000 --reload &
  INFO:     Uvicorn running on http://0.0.0.0:5000

A: Done. The API is now running with FastAPI + PostgreSQL:
  - `/home/computron/todo_api/app.py` — FastAPI with async CRUD endpoints
  - `/home/computron/todo_api/models.py` — SQLAlchemy async with PostgreSQL via asyncpg
  - `/home/computron/todo_api/.env` — Database connection string
  - Docs at http://127.0.0.1:5000/docs

user: Can you add authentication? I want JWT-based auth with login/register endpoints.
```

## Required Facts

| Fact | Anchored pattern |
|------|-----------------|
| Project directory | `r"/home/computron/todo_api"` |
| FastAPI framework (NOT Flask) | `r"[Ff]ast[Aa][Pp][Ii]"` |
| PostgreSQL database (NOT SQLite) | `r"[Pp]ostgre"` |
| Flask was abandoned | `r"[Ff]lask.*replaced|switched.*[Ff]ast|replaced.*[Ff]lask|was.*[Ff]lask|originally.*[Ff]lask"` |
| SQLite was abandoned | `r"[Ss][Qq][Ll]ite.*replaced|switched.*[Pp]ostgre|replaced.*[Ss][Qq][Ll]ite|was.*[Ss][Qq][Ll]ite|originally.*[Ss][Qq][Ll]ite"` |
| app.py file | `r"app\.py"` |
| models.py file | `r"models\.py"` |
| .env file with DATABASE_URL | `r"\.env|DATABASE_URL"` |
| Uvicorn server | `r"uvicorn"` |
| API docs at /docs | `r"/docs"` |
| asyncpg driver | `r"asyncpg"` |

## Probes

The critical risk with redirects is the agent reverting to the abandoned approach. After compaction, if the summary says "built a Flask API" without noting the pivot, the agent might add JWT auth to a Flask app that no longer exists.

- **Probe 1** (anti-revert — critical): The user pivoted from Flask to FastAPI. If the agent doesn't know this, it adds JWT auth with Flask patterns.
- **Probe 2** (anti-revert — critical): The user pivoted from SQLite to PostgreSQL. If the agent uses SQLite for the auth tables, it won't work.
- **Probe 3** (forward action): The user asked for JWT auth. The agent needs to know the current stack to implement it correctly.
- **Probe 4** (file awareness): The agent needs to know which files exist and their current state to add auth.

| Question | Pass pattern | Fail pattern |
|----------|-------------|-------------|
| What web framework is the API currently using? | `r"[Ff]ast[Aa][Pp][Ii]"` | — |
| What database is the API currently using? | `r"[Pp]ostgre"` | — |
| What should you do next? | `r"JWT|auth|login|register|token"` | — |
| What files exist in the project? | `r"app\.py|models\.py|todo_api"` | — |
