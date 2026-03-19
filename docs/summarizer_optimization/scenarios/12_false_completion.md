# Scenario 12: False Completion on Multi-Step Tasks

## Purpose

Tests whether the summarizer correctly identifies remaining work when a multi-step task is partially completed. This catches a production failure where the summarizer wrote "Remaining Work: None" when 2 of 6 test pages were still incomplete.

The key challenge: the conversation is dominated by completed work with lots of tool output noise. The dashboard showing progress was only seen briefly early on and is buried under many subsequent messages. The assistant never explicitly states "I still need to do tasks 4 and 5" — the summarizer must infer this from the dashboard snapshot and the fact that only 3 of 5 tasks were worked on.

**Minimum threshold**: 75%

## Conversation

```
user: go to the test page and complete all the tasks

A: I'll open the test page and work through each task.
[Called tools: page_snapshot]

tool(page_snapshot): [Page: Task Dashboard | http://localhost:8080/tests/dashboard.html | ]
Task Dashboard - Complete all 5 tasks to pass

Task 1: Form Submission ✗
Task 2: Data Entry ✗
Task 3: File Upload ✗
Task 4: Search & Filter ✗
Task 5: Review & Submit ✗

Progress: 0/5 complete
[Complete All Tasks] button (disabled)

A: I can see 5 tasks on the dashboard. Let me start with Task 1.
[Called tools: click]

tool(click): Clicked "Task 1: Form Submission"

A: [Called tools: page_snapshot]

tool(page_snapshot): [Page: Task 1: Form Submission | http://localhost:8080/tests/task1.html | ]
Form Submission
Name: [___________]
Email: [___________]
Phone: [___________]
Address: [___________]
[Submit]

A: I'll fill in the form fields.
[Called tools: fill_field, fill_field, fill_field, fill_field]

tool(fill_field): Filled "Name" with "John Smith"
tool(fill_field): Filled "Email" with "john@example.com"
tool(fill_field): Filled "Phone" with "555-0123"
tool(fill_field): Filled "Address" with "123 Main St, Austin TX"

A: Now I'll submit the form.
[Called tools: click]

tool(click): Clicked "Submit"

A: [Called tools: page_snapshot]

tool(page_snapshot): [Page: Task 1: Form Submission | http://localhost:8080/tests/task1.html | ]
✓ Task 1 Complete!

A: Done. Moving to Task 2.
[Called tools: click]

tool(click): Clicked "Back to Dashboard"

A: [Called tools: click]

tool(click): Clicked "Task 2: Data Entry"

A: [Called tools: page_snapshot]

tool(page_snapshot): [Page: Task 2: Data Entry | http://localhost:8080/tests/task2.html | ]
Data Entry - Enter product inventory
Row 1: Product [___] | Price [___] | Qty [___] | SKU [___]
Row 2: Product [___] | Price [___] | Qty [___] | SKU [___]
Row 3: Product [___] | Price [___] | Qty [___] | SKU [___]
[Save All]

A: I need to fill in three rows of inventory data.
[Called tools: fill_field, fill_field, fill_field, fill_field]

tool(fill_field): Filled Row 1 Product with "Widget A"
tool(fill_field): Filled Row 1 Price with "29.99"
tool(fill_field): Filled Row 1 Qty with "10"
tool(fill_field): Filled Row 1 SKU with "WA-001"

A: [Called tools: fill_field, fill_field, fill_field, fill_field]

tool(fill_field): Filled Row 2 Product with "Widget B"
tool(fill_field): Filled Row 2 Price with "49.99"
tool(fill_field): Filled Row 2 Qty with "5"
tool(fill_field): Filled Row 2 SKU with "WB-002"

A: [Called tools: fill_field, fill_field, fill_field, fill_field]

tool(fill_field): Filled Row 3 Product with "Widget C"
tool(fill_field): Filled Row 3 Price with "19.99"
tool(fill_field): Filled Row 3 Qty with "20"
tool(fill_field): Filled Row 3 SKU with "WC-003"

A: All rows filled. Saving.
[Called tools: click]

tool(click): Clicked "Save All"

A: [Called tools: page_snapshot]

tool(page_snapshot): [Page: Task 2: Data Entry | http://localhost:8080/tests/task2.html | ]
✓ Task 2 Complete! All 3 rows saved successfully.

A: Task 2 done. On to Task 3.
[Called tools: click]

tool(click): Clicked "Back to Dashboard"

A: [Called tools: click]

tool(click): Clicked "Task 3: File Upload"

A: [Called tools: page_snapshot]

tool(page_snapshot): [Page: Task 3: File Upload | http://localhost:8080/tests/task3.html | ]
Task 3: File Upload
Upload requirements:
- File must be .txt or .csv format
- Maximum size: 1MB
- File must contain at least 3 lines of data
[Choose File] No file selected
[Upload]

A: I need to create a valid file that meets the requirements.
[Called tools: bash]

tool(bash): Created /tmp/test_data.csv with 5 lines of CSV data

A: [Called tools: file_upload]

tool(file_upload): Uploaded /tmp/test_data.csv to the file input

A: [Called tools: click]

tool(click): Clicked "Upload"

A: [Called tools: page_snapshot]

tool(page_snapshot): [Page: Task 3: File Upload | http://localhost:8080/tests/task3.html | ]
✓ Task 3 Complete! File "test_data.csv" uploaded and validated.

A: Task 3 complete. Let me check the validation details.
[Called tools: page_snapshot]

tool(page_snapshot): [Page: Task 3: File Upload | http://localhost:8080/tests/task3.html | ]
✓ Task 3 Complete!
File validation results:
- Format: CSV ✓
- Size: 245 bytes ✓
- Lines: 5 (minimum 3) ✓
- Headers detected: name, email, phone ✓
All checks passed.
[Back to Dashboard]

A: All validation checks passed. The file had proper CSV format with headers.
[Called tools: click]

tool(click): Clicked "Back to Dashboard"
```

## Required Facts

| Fact | Pattern |
|------|---------|
| Task 1 mentioned | `r"[Tt]ask 1"` |
| Task 2 mentioned | `r"[Tt]ask 2"` |
| Task 3 mentioned | `r"[Tt]ask 3"` |
| Dashboard URL | `r"dashboard"` |
| Tasks 4 or 5 mentioned as remaining | `r"[Tt]ask [45]"` |

## Probes

| Question | Pass Pattern | Fail Pattern |
|----------|-------------|-------------|
| What tasks still need to be completed? List them. | `r"[Tt]ask 4"` | `r"[Aa]ll.*complete|[Nn]o.{0,10}remain|remaining.*[Nn]one"` |
| How many tasks are done and how many remain? | `r"3.*(?:done|complete)|2.*(?:remain|left)"` | `r"5.{0,5}(?:done|complete)|[Aa]ll.*done"` |
| What should the agent do next? | `r"[Tt]ask 4|[Ss]earch"` | `r"all.{0,10}done|nothing|no.{0,10}task"` |
