# The Ringmaster's Complete Tour - Browser Circus

Welcome to the Browser Circus! This guide walks you through all three shows, testing every browser tool along the way. Navigate between pages using the playbill nav bar at the top of each page.

**How it works:** Each page has a "Ringmaster's Script" panel at the top with numbered steps. Each step has a status indicator: **[PENDING]**, **[PASS]**, or **[FAIL]**. After performing each step, re-read the program panel to check that the step turned [PASS]. If it stays [PENDING], retry the action. The final step on each page links to the next show — it unlocks automatically when all other steps pass.

---

## Act I: The Big Top

**URL:** `browser_circus/big_top.html`

### Tools: `click`, `fill_field`, `select_option`, `read_page`, `scroll_page`, `press_keys`

1. **Open the page.** Use `open_url` to navigate to `big_top.html`.
2. **Read the Show Program.** Use `read_page` to see the numbered steps at the top.
3. **Click "Continue to Dashboard"** (the primary CTA). Verify the Announcer's Scroll logs the click.
4. **Click "Maybe Later"** (secondary CTA). Verify a log entry appears.
5. **Click "View Pricing"** link. Verify the page scrolls to the pricing section.
6. **Fill the Ticket Booth form:**
   - Fill "Full Name" with "Ada Lovelace"
   - Fill "Email" with "ada@circus.com"
   - Select "Performer" from the Role dropdown
   - Check "Receive Updates"
   - Select "Carrier Pigeon" radio button
   - Fill "Bio" with "Tightrope specialist and mathematician"
7. **Click "Buy Tickets!"** and verify the form status spotlight turns on.
8. **Read the Performers Roster** table. List all performers, their roles, and acts.
9. **Click "Edit" next to Alice Smith.** Verify the log entry.
10. **Open "Bearded Lady's Bio"** details element. Read the hidden content.
11. **Type in the Guest Book** contenteditable area.
12. **Scope test:** In The Three Rings, click "Red Spotlight" in the Red Ring only.
13. **Scroll through The Grand Parade.** Use `scroll_page` to navigate all 5 sections. Read each marker.

---

## Act II: The Daredevil Show

**URL:** `browser_circus/daredevil_show.html`

### Tools: `perform_visual_action` (click, double-click, right-click, type, scroll, drag), `press_keys`

1. **Navigate** from big_top.html to daredevil_show.html using the nav bar.
2. **Click the "Launch!" button** (Stunt 1). Verify click-status says "LAUNCHED!".
3. **Double-click the "Catch!" target** (Stunt 2). Verify the counter increments.
4. **Right-click the "Reveal!" target** (Stunt 3). Verify status says "Revealed!".
5. **Type "Hello Circus!"** in the tightrope input (Stunt 4). Verify type-status updates.
6. **Scroll inside** the Wheel of Death container (Stunt 5). Verify scroll-status updates.
7. **Drag the acrobat** to the platform (Stunt 6). Verify drag-status says "Landed!".
8. **HTML5 drag-and-drop:** Drag the juggling prop to the drop zone (Stunt 7).
9. **Press and hold** the strongman button for 500ms+ (Stunt 8). Verify it turns green.
10. **Test downloads** (Stunt 9): Click the direct file link, then the blob download button.
11. **Press Enter** on the hotkey target (Stunt 10). Verify the event log.
12. **Use `go_back`** to return to big_top.html.

---

## Act III: The Shadow Tent

**URL:** `browser_circus/shadow_tent.html`

### Tools: `click`, `fill_field`, `select_option`, `read_page`

1. **Navigate** to shadow_tent.html using the nav bar.
2. **Click "Shadow Button"** inside the open shadow root (Illusion 1). Verify the event log.
3. **Read the text** inside the open shadow root.
4. **Click the deeply nested "Inner Button"** (Illusion 2) — crosses 2 shadow boundaries.
5. **Read the slotted content** in The Slot Machine (Illusion 3) — title and subtitle.
6. **Fill the shadow form** (Illusion 4):
   - Name: "Houdini"
   - Select: "Silk Scarves"
   - Check the volunteer checkbox
7. **Click both buttons** in Half and Half (Illusion 5) — light DOM and shadow DOM.
8. **Observe The Sealed Vault** (Illusion 6) — closed shadow root limitations.
9. **Click the fancy-button** custom element (Illusion 7).
10. **Read slotted content** through the Russian Dolls (Illusion 8) — two-level delegation.
11. **Verify content visibility** in The Invisible Box (Illusion 9) — display:contents host.
12. **Click the triple-nested button** (Illusion 10) — 3 shadow levels deep.
13. **Read named slot content** across boundaries (Illusion 11).
14. **Use `go_back`** to return to the previous page.

---

## Finale

After completing all three acts, the browser agent has tested:
- Basic interactions (click, fill, select, type)
- Form submission and validation
- Table reading
- Link navigation and hash anchors
- Scroll detection (page-level and container)
- Visual/pointer actions (click, double-click, right-click, drag)
- HTML5 drag-and-drop
- Press-and-hold interactions
- File downloads (direct, attribute, blob)
- Keyboard shortcuts
- Shadow DOM traversal (open, closed, nested)
- Slot projection and re-projection
- Custom elements
- display:contents hosts
- Cross-page navigation (open_url, go_back)
- Scoped element selection

Take a bow! The show is complete.
