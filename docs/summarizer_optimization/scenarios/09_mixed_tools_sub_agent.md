# Scenario 09: Mixed Tool Types (SUB_AGENT browsing + coding)

## Purpose

Tests a SUB_AGENT that both browses the web AND writes code in the same session. Real sub-agents often combine research (browsing for API docs, examples) with implementation (writing code, running tests). The summarizer needs to preserve both the research findings AND the code state.

## Conversation

Agent is tasked with finding a weather API and building a simple forecast tool.

```
system: You are a worker agent with file, terminal, and browser tools. Complete the task and return file paths in your summary.

user: Find a free weather API that doesn't require authentication, then write a Python script that fetches the 5-day forecast for Austin, TX and saves it as a formatted report.

A: Let me find a suitable free weather API first.
  [Called tools: browser_agent_tool]

tool (browser_agent_tool): Researched free weather APIs. Found:
  1. Open-Meteo (https://open-meteo.com) — free, no API key needed, REST API
  2. wttr.in — free, no key, simple curl-based
  3. OpenWeatherMap — free tier but requires API key

  Open-Meteo is the best fit: completely free, no auth, good documentation.
  API endpoint: https://api.open-meteo.com/v1/forecast?latitude=30.27&longitude=-97.74&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=America/Chicago&forecast_days=5

A: Good, Open-Meteo is perfect. Let me write the script.
  [Called tools: write_file]

tool (write_file): Created /home/computron/weather_forecast/forecast.py

A: [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ cd /home/computron/weather_forecast && python forecast.py
  Traceback (most recent call last):
    File "forecast.py", line 3, in <module>
      import requests
  ModuleNotFoundError: No module named 'requests'

A: Need to install requests first.
  [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ pip install requests
  Successfully installed requests-2.31.0

A: [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ cd /home/computron/weather_forecast && python forecast.py
  Traceback (most recent call last):
    File "forecast.py", line 15, in <module>
      data = response.json()["daily"]
  KeyError: 'daily'

A: The API response format must be different. Let me check what it actually returns.
  [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ curl -s "https://api.open-meteo.com/v1/forecast?latitude=30.27&longitude=-97.74&daily=temperature_2m_max,temperature_2m_min,precipitation_sum&timezone=America/Chicago&forecast_days=5" | python -m json.tool | head -30
  {
    "latitude": 30.25,
    "longitude": -97.75,
    "generationtime_ms": 0.05,
    "utc_offset_seconds": -18000,
    "timezone": "America/Chicago",
    "daily_units": {
      "time": "iso8601",
      "temperature_2m_max": "°C",
      "temperature_2m_min": "°C",
      "precipitation_sum": "mm"
    },
    "daily": {
      "time": ["2025-03-17", "2025-03-18", "2025-03-19", "2025-03-20", "2025-03-21"],
      "temperature_2m_max": [28.5, 26.3, 24.1, 27.8, 30.2],
      "temperature_2m_min": [15.2, 14.8, 12.5, 16.1, 17.3],
      "precipitation_sum": [0.0, 2.5, 5.1, 0.0, 0.0]
    }
  }

A: The API works, the data is there. The issue was in my parsing code — the response has a top-level "daily" key. Let me fix the script.
  [Called tools: write_file]

tool (write_file): Updated /home/computron/weather_forecast/forecast.py

A: [Called tools: run_bash_cmd]

tool (run_bash_cmd): $ cd /home/computron/weather_forecast && python forecast.py
  5-Day Weather Forecast for Austin, TX
  ======================================
  Mon Mar 17: High 83°F / Low 59°F — Sunny
  Tue Mar 18: High 79°F / Low 59°F — Rain (2.5mm)
  Wed Mar 19: High 75°F / Low 55°F — Rain (5.1mm)
  Thu Mar 20: High 82°F / Low 61°F — Sunny
  Fri Mar 21: High 86°F / Low 63°F — Sunny

  Report saved to: /home/computron/weather_forecast/forecast_report.txt

A: The script works. Here's a summary:

  **Created files**:
  - `/home/computron/weather_forecast/forecast.py` — Python script that fetches and formats the forecast
  - `/home/computron/weather_forecast/forecast_report.txt` — Generated report

  **API used**: Open-Meteo (https://api.open-meteo.com) — free, no authentication required

  **Issues encountered and fixed**:
  - Had to install `requests` module
  - Fixed JSON parsing — the API response has a top-level "daily" key, not nested under "forecast"
  - Temperatures are returned in Celsius, converted to Fahrenheit in the report

user: Can you also add humidity to the report?
```

## Required Facts

| Fact | Anchored pattern |
|------|-----------------|
| Open-Meteo API | `r"[Oo]pen.?[Mm]eteo"` |
| API URL | `r"api\.open-meteo\.com"` |
| No authentication needed | `r"no.*auth|no.*key|free|no.*API key"` |
| Script path | `r"forecast\.py"` |
| Report path | `r"forecast_report\.txt"` |
| Austin TX location | `r"[Aa]ustin"` |
| Requests module installed | `r"requests"` |
| KeyError fix — daily key | `r"daily|KeyError|JSON|parsing"` |
| Celsius to Fahrenheit conversion | `r"[Cc]elsius|[Ff]ahrenheit|convert"` |
| Working directory | `r"/home/computron/weather_forecast"` |

## Probes

The agent combined browsing (API research) with coding (script writing) and debugging (2 errors). All three types of work must survive compaction for the agent to continue.

- **Probe 1** (forward action): User asked to add humidity. The agent needs to know the API, the script path, and the current report format to make this change.
- **Probe 2** (anti-loop): The agent already found and chose Open-Meteo. If it lost this, it would re-research APIs.
- **Probe 3** (anti-loop): The agent debugged two errors (missing requests, wrong JSON key). If it re-introduces either bug while adding humidity, it would loop.
- **Probe 4** (cross-tool context): The agent used browser tools to find the API and coding tools to build the script. Both need to survive in one summary.

| Question | Pass pattern | Fail pattern |
|----------|-------------|-------------|
| What file would you modify to add humidity to the report? | `r"forecast\.py"` | `r"create.*new|start.*from scratch"` |
| What weather API are you using and does it need authentication? | `r"[Oo]pen.?[Mm]eteo.*no.*auth|[Oo]pen.?[Mm]eteo.*free|no.*key.*[Oo]pen.?[Mm]eteo"` | `r"search.*API|find.*API|need to research"` |
| What errors did you encounter while building the script? | `r"requests|KeyError|daily|module|import"` | — |
| Where are the project files located? | `r"/home/computron/weather_forecast"` | — |
