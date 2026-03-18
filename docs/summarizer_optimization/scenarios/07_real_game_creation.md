# Scenario 07: Real Game Creation (Heavy Metal Nightmare)

## Purpose

Tests compaction on a real coding agent conversation — not synthetic. This is a 213-message session where the agent created an HTML game with multiple levels, generated images, set up a Git repo, and pushed to GitHub. It exercises the summarizer on real tool outputs (file writes, bash commands, image generation) at scale (40k chars serialized).

This scenario was NOT designed for testing — it's a real conversation captured as-is. The probes test whether the agent could continue working on the game after compaction.

## Source

Conversation ID: `fe2c2c46-dce5-4239-b49d-676a70c654a2`

The conversation is too large to inline (213 messages, 82k chars raw, 40k serialized). The test runner loads it directly from the conversation history file.

## Compaction Boundary Analysis

With `keep_recent=6`:
- **Total non-system messages**: 212 (18 user, 92 assistant, 102 tool)
- **Compacted**: 205 messages — the entire game creation process
- **Kept**: Last 6 messages — README creation and a user question about ASCII art
- **Serialized size**: 40,384 chars (right at the 40k budget — progressive shrink triggers)

## Key Information That Must Survive

The compacted region contains everything about the game:
- Game name and concept (Heavy Metal Nightmare)
- Game architecture (single HTML file, 59KB)
- 3 levels: Cemetery of Shadows, Hell's Forge, The Abyssal Throne
- Controls: WASD/arrows, space to attack
- Generated assets: title_screen.png, player sprites
- GitHub repo and live URL
- File paths on disk

## Probes

This is a real conversation, so the probes test practical continuity: could the agent continue modifying the game after compaction?

- **Probe 1** (forward action): The user's last question is about ASCII art in the README. But after that, they might ask to modify the game. The agent needs to know the game exists and where the files are.
- **Probe 2** (anti-loop): The agent already created the game, generated images, and pushed to GitHub. If it doesn't know this, it would try to create the game from scratch.
- **Probe 3** (context): The agent needs to know the file structure to make changes. If the user says "add a 4th level," the agent needs to know game.html is the main file and how levels work.

| Question | Pass pattern | Fail pattern |
|----------|-------------|-------------|
| What game did you create and where are the files? | `r"[Hh]eavy [Mm]etal.*[Nn]ightmare|game\.html"` | — |
| Have you already created and deployed the game, or do you still need to build it? | `r"already|created|deployed|pushed|github|complete"` | `r"need to create|should create|haven.t started"` |
| If the user asks you to add a 4th level, what file would you modify? | `r"game\.html"` | — |
