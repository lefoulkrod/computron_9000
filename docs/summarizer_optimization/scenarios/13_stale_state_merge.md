# Scenario 13: Stale Current State During Merge

## Purpose

Tests whether the summarizer updates the Current State section when merging a prior summary with new messages. In production, compaction 2 of a browser test conversation copied "Test 4 is currently being worked on" from the prior summary even though the agent had moved on to Test 5. The summarizer should reconcile the prior summary's state with evidence from new messages.

This is distinct from scenario 08 (merge degradation) which tests whether *facts* survive merges. This tests whether *state* gets updated.

**Minimum threshold**: 75%

## Conversation

### Phase 1: Complete tasks A and B, working on C

```
system: You are a helpful assistant that completes tasks on web pages.

user: Complete all 5 tasks on the task board

A: I'll start with Task A.
[Called tools: page_snapshot]

tool(page_snapshot): [Page: Task Board | http://localhost:3000/tasks | ]
Task Board — 5 tasks remaining
Task A: Write report ✗
Task B: Review PR ✗
Task C: Update docs ✗
Task D: Fix bug #421 ✗
Task E: Deploy staging ✗

A: Starting with Task A: Write report.
[Called tools: click]

tool(click): Clicked "Task A"

A: [Called tools: fill_field]

tool(fill_field): Filled report content

A: [Called tools: click]

tool(click): Clicked "Submit"

A: Task A complete. The quarterly report has been submitted with revenue figures ($4.2M Q1, $4.8M Q2). Moving to Task B.
[Called tools: click]

tool(click): Clicked "Task B: Review PR"

A: [Called tools: page_snapshot]

tool(page_snapshot): [Page: PR #287 Review | http://localhost:3000/pr/287 | ]
PR #287: Refactor auth middleware
Files changed: 4
+127 -89 lines

A: Reviewing PR #287. The auth middleware refactor looks good — replaces session tokens with JWTs, adds refresh token rotation.
[Called tools: click]

tool(click): Clicked "Approve"

A: PR #287 approved. Task B complete. Now moving to Task C: Update docs.
[Called tools: click]

tool(click): Clicked "Task C: Update docs"

A: [Called tools: page_snapshot]

tool(page_snapshot): [Page: Documentation Editor | http://localhost:3000/docs/api | ]
API Documentation v2.3
Last updated: 2026-01-15
Sections: Authentication, Endpoints, Rate Limits, Errors

A: I need to update the authentication section to reflect the JWT changes from PR #287.
[Called tools: fill_field]

tool(fill_field): Updated Authentication section with JWT details

A: I've updated the auth section. Now I need to update the rate limits section with the new values from the sprint planning doc.
[Called tools: scroll_page]

tool(scroll_page): Scrolled to Rate Limits section
```

### Phase 2: Finish C, complete D, start E

```
A: The rate limits section has been updated. Submitting the docs update.
[Called tools: click]

tool(click): Clicked "Save & Publish"

A: Task C complete — docs updated with JWT auth and new rate limits (100 req/min for free tier, 1000 for paid). Moving to Task D.
[Called tools: click]

tool(click): Clicked "Task D: Fix bug #421"

A: [Called tools: page_snapshot]

tool(page_snapshot): [Page: Bug #421 | http://localhost:3000/bugs/421 | ]
Bug #421: Login fails after password reset
Status: Open
Assigned: AI Assistant
Priority: High

A: I'll fix the login bug. The issue is that the password hash isn't being updated in the session cache after reset.
[Called tools: execute_javascript]

tool(execute_javascript): Applied fix to session cache invalidation

A: [Called tools: click]

tool(click): Clicked "Run Tests"

A: [Called tools: page_snapshot]

tool(page_snapshot): [Page: Bug #421 | http://localhost:3000/bugs/421 | ]
Bug #421: Login fails after password reset
Status: Fixed ✓
Tests: 14/14 passing

A: Bug #421 fixed — session cache invalidation after password reset. All 14 tests passing. Task D complete. Moving to Task E: Deploy staging.
[Called tools: click]

tool(click): Clicked "Task E: Deploy staging"

A: [Called tools: page_snapshot]

tool(page_snapshot): [Page: Deploy Pipeline | http://localhost:3000/deploy | ]
Deploy to Staging
Branch: main (3 commits ahead)
Last deploy: 2026-03-18 14:30
Status: Ready

A: Starting the staging deployment. I need to run the pre-deploy checks first.
[Called tools: click]

tool(click): Clicked "Run Pre-Deploy Checks"

A: Pre-deploy checks are running. Waiting for the health check and migration validation to complete.
[Called tools: page_snapshot]

tool(page_snapshot): [Page: Deploy Pipeline | http://localhost:3000/deploy | ]
Pre-Deploy Checks:
✓ Unit tests passed
✓ Integration tests passed
✗ Migration check — pending (running...)
```

## Required Facts

| Fact | Pattern |
|------|---------|
| Task A completed | `r"[Tt]ask A.*(?:complete|done|report)"` |
| Task B completed | `r"[Tt]ask B.*(?:complete|done|PR|approve)"` |
| Task C completed | `r"[Tt]ask C.*(?:complete|done|docs)"` |
| Task D completed | `r"[Tt]ask D.*(?:complete|done|fix|bug)"` |
| Revenue figures | `r"4\.2.*4\.8|4\.8.*4\.2"` |
| PR number | `r"287"` |
| Rate limits | `r"100.*1000|1000.*100"` |
| Bug number | `r"421"` |
| Task E in progress | `r"[Tt]ask E|[Dd]eploy|[Ss]taging"` |

## Probes

| Question | Pass Pattern | Fail Pattern |
|----------|-------------|-------------|
| What is the agent currently working on? | `r"[Tt]ask E|[Dd]eploy|[Ss]taging"` | `r"[Tt]ask [ABCD]\b.*(?:working|current|now)|[Uu]pdat.*docs"` |
| What tasks are done and what remains? | `r"[Tt]ask [ED]|[Dd]eploy|[Bb]ug"` | `r"[Aa]ll 5.*done|[Nn]one.*remain"` |
| What was the last thing completed before the current task? | `r"[Tt]ask D|[Bb]ug.*421|[Ss]ession.*cache"` | — |
| What page is the agent on right now? | `r"[Dd]eploy|[Pp]ipeline|[Ss]taging"` | `r"[Dd]oc|[Bb]ug|[Tt]ask [Bb]oard"` |
