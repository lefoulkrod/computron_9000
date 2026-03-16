# Scenario 02: Desktop GUI Workflow

## Purpose

Tests that the summarizer preserves stateful GUI context: which application is open, what data has been entered, what the screen looks like, and what coordinates/elements are available. Desktop agent conversations have a fundamentally different shape from text-based agents — they involve coordinate-based interactions, screenshot OCR results, and application state that the agent can't re-derive without looking at the screen again.

## Agent Type

DESKTOP_AGENT

## Conversation

Agent is asked to create a budget spreadsheet in LibreOffice Calc.

```
system: You are an AI assistant that controls a desktop computer. You can see the screen via read_screen() and interact via mouse and keyboard tools. Resolution: 1280x720.

user: Open LibreOffice Calc and create a simple monthly budget spreadsheet with income and expenses categories. Put some example numbers in.

assistant: Let me start by opening LibreOffice Calc.
  [Called tools: run_bash_cmd]

tool (run_bash_cmd): Started /usr/bin/libreoffice --calc
  PID: 4521

assistant: Let me wait a moment for it to load, then check the screen.
  [Called tools: read_screen]

tool (read_screen): [Screen: 1280x720]
  LibreOffice Calc - Untitled 1
  [Menu bar at top]
  [1] File menu (42, 11)
  [2] Edit menu (85, 11)
  [3] View menu (126, 11)
  [4] Insert menu (170, 11)
  [5] Format menu (224, 11)
  Active cell: A1
  [6] Name Box showing "A1" (52, 52)
  [7] Formula bar (empty) (400, 52)
  [Grid of empty cells visible]
  [8] Cell A1 (selected) (75, 82)
  [9] Cell B1 (175, 82)
  [10] Cell C1 (275, 82)
  [Sheet tabs at bottom]
  [11] Sheet1 tab (active) (45, 698)

assistant: LibreOffice Calc is open. I'll start by creating headers. Let me type the title first.
  [Called tools: keyboard_type]

tool (keyboard_type): Typed "Monthly Budget" into active element

assistant: Now I'll move to A3 for the first category header and set up the structure.
  [Called tools: mouse_click]

tool (mouse_click): Clicked at (75, 122)

assistant: [Called tools: keyboard_type]

tool (keyboard_type): Typed "Category"

assistant: [Called tools: mouse_click]

tool (mouse_click): Clicked at (175, 122)

assistant: [Called tools: keyboard_type]

tool (keyboard_type): Typed "Amount"

assistant: Now I'll enter the income section. Let me click cell A4.
  [Called tools: mouse_click]

tool (mouse_click): Clicked at (75, 142)

assistant: [Called tools: keyboard_type]

tool (keyboard_type): Typed "INCOME"

assistant: [Called tools: mouse_click, keyboard_type]

tool (mouse_click): Clicked at (75, 162)
tool (keyboard_type): Typed "Salary"

assistant: [Called tools: mouse_click, keyboard_type]

tool (mouse_click): Clicked at (175, 162)
tool (keyboard_type): Typed "5000"

assistant: [Called tools: mouse_click, keyboard_type]

tool (mouse_click): Clicked at (75, 182)
tool (keyboard_type): Typed "Freelance"

assistant: [Called tools: mouse_click, keyboard_type]

tool (mouse_click): Clicked at (175, 182)
tool (keyboard_type): Typed "1200"

assistant: Now the expenses section.
  [Called tools: mouse_click, keyboard_type]

tool (mouse_click): Clicked at (75, 212)
tool (keyboard_type): Typed "EXPENSES"

assistant: [Called tools: mouse_click, keyboard_type, mouse_click, keyboard_type, mouse_click, keyboard_type, mouse_click, keyboard_type, mouse_click, keyboard_type, mouse_click, keyboard_type]

tool (mouse_click): Clicked at (75, 232)
tool (keyboard_type): Typed "Rent"
tool (mouse_click): Clicked at (175, 232)
tool (keyboard_type): Typed "1500"
tool (mouse_click): Clicked at (75, 252)
tool (keyboard_type): Typed "Groceries"
tool (mouse_click): Clicked at (175, 252)
tool (keyboard_type): Typed "600"
tool (mouse_click): Clicked at (75, 272)
tool (keyboard_type): Typed "Utilities"
tool (mouse_click): Clicked at (175, 272)
tool (keyboard_type): Typed "200"

assistant: Let me add a few more expenses and then create totals. Let me check the current state.
  [Called tools: read_screen]

tool (read_screen): [Screen: 1280x720]
  LibreOffice Calc - Untitled 1
  [Menu bar at top]
  Active cell: B14
  [6] Name Box showing "B14" (52, 52)
  Cell contents visible:
    A1: "Monthly Budget"
    A3: "Category" | B3: "Amount"
    A4: "INCOME"
    A5: "Salary" | B5: "5000"
    A6: "Freelance" | B6: "1200"
    A8: "EXPENSES"
    A9: "Rent" | B9: "1500"
    A10: "Groceries" | B10: "600"
    A11: "Utilities" | B11: "200"
  [8] Cell A1 (75, 82)
  [11] Sheet1 tab (active) (45, 698)

assistant: Good. Now I'll add more expense categories and totals.
  [Called tools: mouse_click, keyboard_type, mouse_click, keyboard_type, mouse_click, keyboard_type, mouse_click, keyboard_type]

tool (mouse_click): Clicked at (75, 292)
tool (keyboard_type): Typed "Transport"
tool (mouse_click): Clicked at (175, 292)
tool (keyboard_type): Typed "350"
tool (mouse_click): Clicked at (75, 312)
tool (keyboard_type): Typed "Insurance"
tool (mouse_click): Clicked at (175, 312)
tool (keyboard_type): Typed "180"

assistant: Now I'll add total formulas. Let me add income total first.
  [Called tools: mouse_click, keyboard_type]

tool (mouse_click): Clicked at (75, 202)
tool (keyboard_type): Typed "Total Income"

assistant: [Called tools: mouse_click, keyboard_type, keyboard_press]

tool (mouse_click): Clicked at (175, 202)
tool (keyboard_type): Typed "=SUM(B5:B6)"
tool (keyboard_press): Pressed Enter

assistant: Now expenses total.
  [Called tools: mouse_click, keyboard_type]

tool (mouse_click): Clicked at (75, 332)
tool (keyboard_type): Typed "Total Expenses"

assistant: [Called tools: mouse_click, keyboard_type, keyboard_press]

tool (mouse_click): Clicked at (175, 332)
tool (keyboard_type): Typed "=SUM(B9:B13)"
tool (keyboard_press): Pressed Enter

assistant: And net balance.
  [Called tools: mouse_click, keyboard_type, mouse_click, keyboard_type, keyboard_press]

tool (mouse_click): Clicked at (75, 362)
tool (keyboard_type): Typed "NET BALANCE"
tool (mouse_click): Clicked at (175, 362)
tool (keyboard_type): Typed "=B7-B15"
tool (keyboard_press): Pressed Enter

assistant: Let me verify everything looks right.
  [Called tools: read_screen]

tool (read_screen): [Screen: 1280x720]
  LibreOffice Calc - Untitled 1
  Active cell: B19
  Cell contents visible:
    A1: "Monthly Budget"
    A3: "Category" | B3: "Amount"
    A4: "INCOME"
    A5: "Salary" | B5: "5000"
    A6: "Freelance" | B6: "1200"
    A7: "Total Income" | B7: "6200"
    A8: "EXPENSES"
    A9: "Rent" | B9: "1500"
    A10: "Groceries" | B10: "600"
    A11: "Utilities" | B11: "200"
    A12: "Transport" | B12: "350"
    A13: "Insurance" | B13: "180"
    A15: "Total Expenses" | B15: "2830"
    A17: "NET BALANCE" | B17: "3370"

assistant: The spreadsheet is set up. Here's a summary:

  **Income**: Salary $5,000 + Freelance $1,200 = **$6,200**
  **Expenses**: Rent $1,500 + Groceries $600 + Utilities $200 + Transport $350 + Insurance $180 = **$2,830**
  **Net Balance**: **$3,370**

  Now let me save the file. I'll use Ctrl+S.
  [Called tools: keyboard_press]

tool (keyboard_press): Pressed Ctrl+S

assistant: [Called tools: read_screen]

tool (read_screen): [Screen: 1280x720]
  Save As dialog
  [20] Filename field: "Untitled 1" (400, 350)
  [21] File type dropdown: "ODS - ODF Spreadsheet (.ods)" (400, 390)
  [22] Save button (580, 450)
  [23] Cancel button (670, 450)
  Current directory: /home/computron/

assistant: I need to give it a proper name. Let me clear the filename and type a new one.
  [Called tools: mouse_click, keyboard_press, keyboard_type, mouse_click]

tool (mouse_click): Clicked at (400, 350)
tool (keyboard_press): Pressed Ctrl+A
tool (keyboard_type): Typed "monthly_budget"
tool (mouse_click): Clicked at (580, 450)

user: Can you also bold the headers and the totals row?
```

## Compaction Boundary Analysis

With `keep_recent=6`:
- **Total messages**: 1 system + ~30 non-system
- **Pinned**: First user message ("Open LibreOffice Calc and create a simple monthly budget...")
- **Compacted**: Messages 2 through ~24 (opening Calc, entering all data, creating formulas, saving)
- **Kept**: Last 6 non-system messages (likely the save dialog, filename entry, and user's follow-up about bolding)
- **Summary must contain**: Complete spreadsheet state (what's in each cell), file save location, that LibreOffice Calc is open

### What crosses the compaction boundary

The user's follow-up ("bold the headers and totals") requires the agent to know:
- Which cells contain headers (A3:B3, A4, A8)
- Which cells contain totals (A7:B7, A15:B15, A17:B17)
- That LibreOffice Calc is open with the file already saved
- The current cell coordinates for these elements

All of this information is ONLY in the compacted messages. The summary must preserve it.

## Required Facts

| Fact | Anchored pattern |
|------|-----------------|
| LibreOffice Calc is open | `r"[Ll]ibre[Oo]ffice\s+[Cc]alc"` |
| Spreadsheet title | `r"[Mm]onthly\s+[Bb]udget"` |
| Salary $5000 | `r"[Ss]alary.*\$?5,?000|\$?5,?000.*[Ss]alary"` |
| Freelance $1200 | `r"[Ff]reelance.*\$?1,?200|\$?1,?200.*[Ff]reelance"` |
| Rent $1500 | `r"[Rr]ent.*\$?1,?500|\$?1,?500.*[Rr]ent"` |
| Total Income $6200 | `r"\$?6,?200"` |
| Total Expenses $2830 | `r"\$?2,?830"` |
| Net Balance $3370 | `r"\$?3,?370"` |
| File saved as monthly_budget | `r"monthly_budget"` |
| SUM formulas used | `r"SUM|formula|calculated|totals?"` |
| Header row location (row 3) | `r"[Hh]eader|[Rr]ow\s*3|[Cc]ategory.*[Aa]mount|A3"` |


## Probes

| Question | Pass pattern | Fail pattern |
|----------|-------------|-------------|
| What should you do next? | `r"bold|format"` | `r"open.*Calc|create.*spreadsheet|enter.*data"` |
| What is the net balance in the spreadsheet? | `r"3.?370"` | — |
| What file are you working on and where is it saved? | `r"monthly_budget"` | — |
