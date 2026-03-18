# Scenario 01: Merge Compaction

## Purpose

Tests that facts from a prior summary survive when merged with new conversation messages during a second compaction. This is where iteration 1 showed the worst results — process narration bled through from prior summaries, and facts were dropped during merging.

## Agent Type

BROWSER_AGENT (shopping)

## Conversation

Two phases. Phase 1 produces a summary. Phase 2 adds new messages, then a second compaction merges the Phase 1 summary with Phase 2 messages.

### Phase 1: Initial product search (produces first summary)

```
system: You are a helpful AI assistant with browser tools.

user: Find me the best noise-cancelling headphones under $400. Compare at least 3 options.

assistant: I'll search for noise-cancelling headphones for you.
  [Called tools: browse_page]

tool (browse_page): [Page: Amazon.com | https://amazon.com | 200]
  [Viewport: 0-900 of 4500px]
  [1] [searchbox] Search Amazon
  [2] [button] Go

assistant: [Called tools: fill_field, click]

tool (fill_field): [Page: Amazon.com | https://amazon.com | 200]
  [1] [searchbox] = noise cancelling headphones
  [2] [button] Go

tool (click): [Page: Amazon.com: noise cancelling headphones | https://amazon.com/s?k=noise+cancelling+headphones | 200]
  [Viewport: 0-900 of 15000px]
  [h2] Results
  [8] [link] Sony WH-1000XM5 Wireless Noise Canceling Headphones
  $278.00 · 4.6 out of 5 stars · 12,847 ratings
  [9] [link] Bose QuietComfort Ultra Headphones
  $349.00 · 4.5 out of 5 stars · 8,234 ratings
  [10] [link] Apple AirPods Max
  $394.99 · 4.3 out of 5 stars · 15,102 ratings
  [11] [link] Sennheiser Momentum 4 Wireless
  $279.95 · 4.4 out of 5 stars · 3,891 ratings
  [12] [link] Sony WH-1000XM4 (Previous Gen)
  $198.00 · 4.7 out of 5 stars · 42,556 ratings

assistant: I found several options. Let me check the top 3 in detail. Starting with the Sony XM5.
  [Called tools: click]

tool (click): [Page: Sony WH-1000XM5 | https://amazon.com/dp/B09XS7JWHH | 200]
  [Viewport: 0-900 of 9000px]
  [h1] Sony WH-1000XM5 Wireless Industry Leading Noise Canceling Headphones
  $278.00
  [13] [button] Add to Cart
  Processor: Integrated Processor V1
  Driver: 30mm carbon fiber composite
  Battery: Up to 30 hours
  Weight: 250g
  Bluetooth: 5.2 with LDAC, AAC, SBC
  ANC: Adaptive Sound Control, 8 microphones
  [h3] Customer Reviews
  4.6 out of 5 stars · 12,847 ratings
  [14] [link] See all reviews

assistant: Now let me check the Bose.
  [Called tools: click]

tool (click): [Page: Bose QuietComfort Ultra | https://amazon.com/dp/B0CCZ26B5V | 200]
  [Viewport: 0-900 of 8500px]
  [h1] Bose QuietComfort Ultra Headphones
  $349.00
  [15] [button] Add to Cart
  ANC: CustomTune technology, Immersive Audio
  Battery: Up to 24 hours
  Weight: 250g
  Bluetooth: 5.3 with aptX Adaptive
  Spatial Audio: Yes, with head tracking
  [h3] Customer Reviews
  4.5 out of 5 stars · 8,234 ratings

assistant: And the Sennheiser.
  [Called tools: click]

tool (click): [Page: Sennheiser Momentum 4 | https://amazon.com/dp/B0BFN4LCC8 | 200]
  [Viewport: 0-900 of 8000px]
  [h1] Sennheiser Momentum 4 Wireless Headphones
  $279.95
  [16] [button] Add to Cart
  Driver: 42mm transducer
  Battery: Up to 60 hours
  Weight: 293g
  Bluetooth: 5.2 with aptX Adaptive, AAC
  ANC: Adaptive Noise Cancellation
  Sound: Customizable EQ via app
  [h3] Customer Reviews
  4.4 out of 5 stars · 3,891 ratings

assistant: Here's my comparison of the top 3 noise-cancelling headphones under $400:

  **Sony WH-1000XM5** — $278.00, 4.6/5 (12,847 ratings)
  - Best overall ANC (8 mics, adaptive)
  - 30h battery, 250g, Bluetooth 5.2 with LDAC

  **Bose QuietComfort Ultra** — $349.00, 4.5/5 (8,234 ratings)
  - Spatial audio with head tracking
  - 24h battery, 250g, Bluetooth 5.3

  **Sennheiser Momentum 4** — $279.95, 4.4/5 (3,891 ratings)
  - Best battery life (60h)
  - 42mm drivers, customizable EQ, 293g

  Best value: Sony XM5. Best battery: Sennheiser. Best features: Bose.
```

**At this point, compaction #1 triggers.** The summary should capture all 3 products with prices, ratings, specs, and URLs.

### Phase 2: User follow-up after first compaction

The test runner automatically feeds the Phase 1 summary as `prior_summary` when summarizing Phase 2. Only new messages are included here:

```
user: The Sony sounds good but I'm worried about comfort for long wearing sessions. Can you check the reviews for comfort complaints?

A: Let me check the Sony XM5 reviews for comfort feedback.
  [Called tools: click]

tool (click): [Page: Sony WH-1000XM5 Reviews | https://amazon.com/product-reviews/B09XS7JWHH | 200]
  [Viewport: 0-900 of 7000px]
  [h2] Customer Reviews
  4.6 out of 5 stars · 12,847 ratings
  [h3] ★★★★★ Best ANC, comfortable for hours
  By AudiophilePro on Feb 20, 2025
  Wore these on a 12-hour flight. No fatigue at all. The headband distributes weight well.
  [h3] ★★★★ Great sound, slightly tight
  By MusicLover on Feb 5, 2025
  ANC is incredible. Only complaint: slightly tight on larger heads for the first week.
  [h3] ★★★ Comfort issues with glasses
  By SpecsWearer on Jan 30, 2025
  Pressure on temples when wearing glasses. Had to return them for the Bose instead.
  [h3] ★★★★★ Most comfortable headphones I've owned
  By DailyCommuter on Jan 15, 2025
  Use these 4+ hours daily. Zero comfort issues. Light at 250g.

A: Based on the reviews, comfort feedback is mostly positive:
  **Positive**: Multiple reviewers report wearing them 4-12 hours without fatigue. The 250g weight and headband design are praised.
  **Concerns**:
  - Slightly tight on larger heads initially (breaks in after a week)
  - Pressure on temples for glasses wearers — one reviewer returned them for Bose
  If you wear glasses, the Bose QC Ultra might be worth considering since it's known for comfort with glasses. Otherwise, the Sony XM5 seems comfortable for most people.

user: Good info. What about the Sennheiser comfort? It's heavier at 293g.

A: [Called tools: browse_page]

tool (browse_page): [Page: Sennheiser Momentum 4 Reviews | https://amazon.com/product-reviews/B0BFN4LCC8 | 200]
  [Viewport: 0-900 of 6000px]
  [h2] Customer Reviews
  [h3] ★★★★ Great sound, noticeable weight
  By StudioPro on Feb 10, 2025
  Sound quality is phenomenal. The 293g is noticeable vs my old XM4s but not uncomfortable.
  [h3] ★★★★★ 60 hours battery is no joke
  By TravelFrequent on Jan 25, 2025
  Comfortable for 6+ hour sessions. The extra weight is worth it for that battery life.
  [h3] ★★★ Ear pads get warm
  By SummerUser on Jan 10, 2025
  In warm weather, the pleather pads make your ears sweat. Otherwise fine.

A: Sennheiser Momentum 4 comfort feedback:
  **Positive**: Comfortable for 6+ hour sessions despite the extra weight. The 60h battery means less charging, less swapping.
  **Concerns**:
  - 293g is noticeably heavier than the Sony (250g)
  - Pleather ear pads can get warm in hot weather
  Overall, the weight difference (43g) is noticeable but not a dealbreaker for most reviewers. If you're in a warm climate, the ear heat could be annoying.
```

## Required Facts

### From Phase 1 (must survive both compactions)

| Fact | Anchored pattern |
|------|-----------------|
| Sony WH-1000XM5 product | `r"Sony\s+WH-1000XM5"` |
| Sony price $278 | `r"\$278"` |
| Sony rating 4.6 | `r"4\.6"` |
| Sony battery 30h | `r"30\s*h"` |
| Sony product URL | `r"amazon\.com/dp/B09XS7JWHH"` |
| Bose QC Ultra product | `r"Bose.*Quiet\s*Comfort"` |
| Bose price $349 | `r"\$349"` |
| Bose rating 4.5 | `r"4\.5"` |
| Bose spatial audio feature | `r"[Ss]patial\s+[Aa]udio"` |
| Sennheiser Momentum 4 product | `r"Sennheiser.*Momentum"` |
| Sennheiser price ~$280 | `r"\$279"` |
| Sennheiser battery 60h | `r"60\s*h"` |

### From Phase 2 (must survive compaction #2)

| Fact | Anchored pattern |
|------|-----------------|
| Sony comfort — glasses issue | `r"[Gg]lasses"` |
| Sony comfort — tight on large heads | `r"tight"` |
| Sennheiser — heavier at 293g | `r"293"` |
| Sennheiser — ear pads warm | `r"warm|sweat|heat"` |
| Bose recommended for glasses | `r"Bose.*glasses|glasses.*Bose|Bose.*comfort.*glasses|glasses.*comfort.*Bose"` |


## Probes

The agent's biggest autonomy risks after this merge compaction: re-searching Amazon (huge waste), re-checking Sony reviews (already done in Phase 2), or not knowing Bose reviews are still needed.

- **Probe 1** (forward action): The agent hasn't checked Bose comfort reviews yet. If it thinks the task is done, the merge lost track of remaining work.
- **Probe 2** (anti-loop): The agent searched Amazon and found 3 products in Phase 1. If the merge dropped this, the agent would re-search from scratch.
- **Probe 3** (anti-loop): The agent checked Sony comfort reviews in Phase 2. If the merge dropped this, the agent would re-check the same reviews.

| Question | Pass pattern | Fail pattern |
|----------|-------------|-------------|
| What should you do next? | `r"Bose.*review|Bose.*comfort|compare"` | `r"search.*Amazon|find.*headphone|start over"` |
| Have you already searched for headphones, or do you need to search? | `r"already|found|Sony|Bose|Sennheiser"` | `r"need to search|should search|haven.t"` |
| Have you already checked Sony comfort reviews? | `r"already|checked|glasses|tight|comfort"` | `r"need to check|should check|haven.t.*review"` |
