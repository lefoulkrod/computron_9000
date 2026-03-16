# Scenario 03: Browser Tool Failure and Retry

## Purpose

Tests that failed tool calls and retry attempts survive compaction. Browser agents frequently encounter stale refs (element no longer exists after page update), page timeouts, and anti-bot blocks. These failures are critical context — the agent needs to know what was tried and failed to avoid retrying the same broken approach.

This directly tests the tension between "no process narration" and "preserve failed approaches."

## Agent Type

BROWSER_AGENT

## Conversation

Agent searches for concert tickets on a ticketing site. Encounters stale refs after a page auto-refreshes, a timeout on a slow page, and eventually succeeds via a different navigation path.

```
system: You are a helpful AI assistant with browser tools.

user: Find me 2 tickets for the Radiohead concert at Madison Square Garden in June. Budget is $300 total.

assistant: I'll search for Radiohead tickets at MSG.
  [Called tools: browse_page]

tool (browse_page): [Page: StubHub - Concert Tickets | https://stubhub.com | 200]
  [Viewport: 0-900 of 5000px]
  [1] [searchbox] Search events
  [2] [button] Search

assistant: [Called tools: fill_field, click]

tool (fill_field): [1] = Radiohead Madison Square Garden

tool (click): [Page: Radiohead Tickets - StubHub | https://stubhub.com/radiohead-new-york-tickets/event/152847 | 200]
  [Viewport: 0-900 of 12000px]
  [h1] Radiohead
  Madison Square Garden · New York, NY
  [h2] Available Dates
  [8] [link] Sat, Jun 14, 2025 — 8:00 PM · from $89/ea
  [9] [link] Sun, Jun 15, 2025 — 8:00 PM · from $112/ea
  [10] [link] Tue, Jun 17, 2025 — 7:30 PM · from $74/ea

assistant: I found 3 dates available. The Jun 17 show has the cheapest tickets starting at $74 each, which fits the $300 budget for 2 tickets. Let me check that one.
  [Called tools: click]

tool (click): [Page: Radiohead - Jun 17 Tickets | https://stubhub.com/radiohead-new-york-tickets/event/152847?eventDate=2025-06-17 | 200]
  [Viewport: 0-900 of 15000px]
  [h1] Radiohead — Tue, Jun 17, 2025 · 7:30 PM
  Madison Square Garden
  [h2] Available Tickets
  [15] [button] Section 226, Row 8 — $74/ea (2 available)
  [16] [button] Section 225, Row 12 — $79/ea (4 available)
  [17] [button] Section 118, Row 22 — $124/ea (2 available)
  [18] [button] Section 105, Row 15 — $148/ea (3 available)
  [19] [link] Show more tickets
  [20] [link] Interactive seat map

assistant: Good options within budget. Section 226 Row 8 at $74 each ($148 total) is the cheapest. Section 118 Row 22 at $124 each ($248 total) also fits. Let me check the seat map to compare views.
  [Called tools: click]

tool (click): Error: Element [20] not found. The page may have refreshed — elements may have changed. Try browse_page to get updated refs.

assistant: The page seems to have refreshed (ticket listings update in real time). Let me get fresh refs.
  [Called tools: browse_page]

tool (browse_page): [Page: Radiohead - Jun 17 Tickets | https://stubhub.com/radiohead-new-york-tickets/event/152847?eventDate=2025-06-17 | 200]
  [Viewport: 0-900 of 15000px]
  [h1] Radiohead — Tue, Jun 17, 2025 · 7:30 PM
  Madison Square Garden
  [h2] Available Tickets
  [1] [button] Section 226, Row 8 — $74/ea (2 available)
  [2] [button] Section 225, Row 12 — $82/ea (4 available)  ← price changed
  [3] [button] Section 118, Row 22 — $124/ea (2 available)
  [4] [button] Section 105, Row 15 — $148/ea (2 available)  ← qty changed
  [5] [link] Show more tickets
  [6] [link] Interactive seat map

assistant: Prices shifted slightly — Section 225 went from $79 to $82. Let me check the seat map now.
  [Called tools: click]

tool (click): Error: Timeout waiting for page load after 30000ms. The page may be loading a heavy interactive element.

assistant: The interactive seat map is too heavy to load. Let me try a different approach — I'll check the section views from the venue page instead.
  [Called tools: browse_page]

tool (browse_page): [Page: MSG Seating Chart | https://stubhub.com/venue/madison-square-garden-475/seating-chart | 200]
  [Viewport: 0-900 of 6000px]
  [h1] Madison Square Garden Seating Chart
  [h2] Section Views
  Section 226: Upper level, behind stage — limited view
  Section 225: Upper level, side — partial view
  Section 118: Lower level, side — good view
  Section 105: Lower level, center — excellent view
  [7] [link] View from Section 226
  [8] [link] View from Section 118

assistant: Important — Section 226 (the cheapest at $74) is behind the stage with limited view. Section 118 at $124 each ($248 total for 2) is lower level with a good view and still under the $300 budget. Let me go back and select those tickets.
  [Called tools: go_back]

tool (go_back): [Page: Radiohead - Jun 17 Tickets | https://stubhub.com/radiohead-new-york-tickets/event/152847?eventDate=2025-06-17 | 200]
  [Viewport: 0-900 of 15000px]
  [h1] Radiohead — Tue, Jun 17, 2025 · 7:30 PM
  [h2] Available Tickets
  [1] [button] Section 226, Row 8 — $74/ea (2 available)
  [2] [button] Section 225, Row 12 — $82/ea (4 available)
  [3] [button] Section 118, Row 22 — $124/ea (2 available)
  [4] [button] Section 105, Row 15 — $148/ea (2 available)

assistant: Here's my recommendation:

  **Best value within budget**: Section 118, Row 22 — $124/ea ($248 total for 2)
  - Lower level, side view — good sightlines
  - Well under the $300 budget

  **Cheapest option**: Section 226, Row 8 — $74/ea ($148 total for 2)
  - BUT: upper level, behind stage — limited view
  - Save money but poor experience

  **Avoid**: Section 105 at $148/ea ($296 total) — technically within budget but leaves almost no margin for fees.

  I'd recommend Section 118. Want me to proceed with selecting those tickets?

user: Yes, go with Section 118.
```

## Compaction Boundary Analysis

With `keep_recent=6`:
- **Total messages**: 1 system + ~20 non-system
- **Pinned**: First user message ("Find me 2 tickets for the Radiohead concert...")
- **Compacted**: Messages 2 through ~14 (initial search, stale ref error, page refresh, timeout error, venue chart workaround, recommendation)
- **Kept**: Last 6 non-system messages (likely the go_back, ticket listing, recommendation, user confirmation)

### What crosses the compaction boundary

The user said "go with Section 118." The agent needs to know:
- That Section 118, Row 22 costs $124/ea on the Jun 17 show
- The page URL and that refs may have changed (prices shift in real time)
- That clicking the interactive seat map times out (don't try it again)
- That Section 226 is behind the stage (if user changes mind and asks "what about the cheap ones?")

The stale ref error and timeout error are in the compacted region. If the summary drops these as "process," the agent might retry the seat map link or get confused by ref changes.

## Required Facts

| Fact | Anchored pattern |
|------|-----------------|
| Radiohead at MSG | `r"[Rr]adiohead.*MSG|[Rr]adiohead.*[Mm]adison|[Rr]adiohead.*concert|[Rr]adiohead.*ticket"` |
| Jun 17 date selected | `r"Jun(?:e)?\s*17"` |
| Section 118, Row 22 recommended | `r"[Ss]ection\s*118"` |
| Price $124/ea | `r"\$?124"` |
| Total $248 for 2 tickets | `r"\$?248|124.*2"` |
| Budget is $300 | `r"\$?300"` |
| Section 226 is behind stage / limited view | `r"226.*behind|226.*limited|behind.*stage|226.*poor|226.*obstruct"` |
| Seat map timed out (don't retry) | `r"[Tt]ime.?out|seat\s*map.*fail|seat\s*map.*slow|couldn.t load|seat\s*map.*error|seat\s*map.*not"` |
| Stale refs happen on this page | `r"[Rr]efresh|stale|refs?\s*chang|prices?\s*(shift|chang|updat)|real.time"` |
| StubHub URL | `r"stubhub\.com"` |
| 3 dates available (Jun 14, 15, 17) | `r"Jun(?:e)?\s*14.*Jun(?:e)?\s*15|Jun(?:e)?\s*14.*Jun(?:e)?\s*17|three\s*dates|3\s*dates"` |


## Probes

| Question | Pass pattern | Fail pattern |
|----------|-------------|-------------|
| What should you do next? | `r"[Ss]ection\s*118|select.*ticket|proceed|purchase"` | `r"seat\s*map|interactive"` |
| Why did you recommend Section 118 over Section 226? | `r"behind.*stage|limited.*view"` | — |
| What dates are available for the Radiohead concert? | `r"Jun.*14|Jun.*15|Jun.*17"` | — |
