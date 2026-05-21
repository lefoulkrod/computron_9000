"""Deep Research skill — multi-agent parallel research with structured output."""

from textwrap import dedent

from sdk.skills import Skill

_SKILL = Skill(
    name="deep_research",
    description="Parallel sub-agent research → structured reports (MD/HTML/PDF)",
    prompt=dedent("""\
        DEEP RESEARCH WORKFLOW — use this skill for any task that asks you to
        "research", "find out about", "look into", or "gather information on"
        a topic. It encodes a proven multi-agent pattern refined across 7+
        real-world research sessions.

        ═══ PHASE 1: PLAN ═══
        Break the topic into 2–5 parallel research areas. Each area should
        be independently researchable by a single sub-agent. Good splits:

        - By subtopic (e.g. "pricing", "features", "competitors")
        - By source (e.g. "official docs", "community reviews", "tutorials")
        - By question (e.g. "what is it?", "how does it compare?", "who uses it?")

        Declare the plan before spawning so the user can adjust.

        ═══ PHASE 2: RESEARCH (spawn in parallel) ═══
        Use spawn_agent for EVERY research sub-agent. Give each agent the
        profile="research_agent" and a SELF-CONTAINED brief that includes:

        - Exact research question/area
        - Specific URLs to visit (if known) or search terms to use
        - What to return: findings, links, quotes, data points
        - Output format: structured markdown with sections
        - A reminder: "Use the browser skill to search and read pages.
          Save screenshots if visual evidence is useful."

        NEVER try to research in your own context — delegate EVERY area.
        Spawn all research agents at once (parallel) before waiting for
        results. Research agents have no context of the bigger picture,
        so each brief must be fully self-contained.

        ═══ PHASE 3: COMPILE ═══
        Once all sub-agents return, compile findings into a structured
        report. Choose format based on what the user needs:

        MARKDOWN REPORT (default):
        - Title + date
        - Executive summary (3–5 bullet takeaways)
        - One section per research area with clear headings
        - Links and citations inline
        - Comparison tables where applicable
        - Save to /home/computron/reports/{topic_slug}.md

        HTML DASHBOARD (for multi-faceted topics or visual needs):
        - Interactive layout with tabs or sections
        - Use existing assets from /home/computron/ — never base64 images
        - Save to /home/computron/projects/{project_name}/index.html

        PDF REPORT (for formal deliverables):
        - Use ReportLab with cover page, TOC, styled tables
        - Consistent color scheme: dark headers, alternating row colors
        - Save to /home/computron/reports/{topic_slug}.pdf

        ═══ PHASE 4: DELIVER ═══
        Call send_file(path) for every generated file.
        Provide a brief summary of key findings in your response.

        ═══ WHEN TO USE THIS SKILL ═══
        Use deep_research when the task is:
        - "Research X" or "find out about X" (open-ended discovery)
        - "Compare X vs Y" (multi-source comparison)
        - "What are the best options for X?" (recommendation research)
        - "Do a deep dive on X" (comprehensive analysis)
        - Any task requiring multiple web sources synthesized together

        Do NOT use deep_research for:
        - Single-fact lookups ("what is the capital of France?")
        - Tasks where one URL has all the answers
        - Quick browsing ("open X and tell me what you see")
        - Code-only tasks (use the coder skill directly)

        ═══ PRO TIPS FROM 92 CONVERSATIONS ═══
        - Research agents sometimes drift — give them specific questions,
          not vague "research X" prompts
        - If a sub-agent times out, spawn a replacement with a narrower scope
        - Screenshots from browser agents are valuable evidence in reports
        - Ask the user "is this enough detail?" before Phase 3 if unsure
        - For multi-city travel research, one agent per city works best
        - For product research, one agent for specs, one for reviews
        - For competitive analysis, one agent per competitor
    """),
    tools=[],  # No new tools — relies on spawn_agent, browser, coder from orchestrator
)
