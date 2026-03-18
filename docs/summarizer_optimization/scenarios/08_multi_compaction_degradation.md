# Scenario 08: Multi-Compaction Degradation

## Purpose

Tests whether facts degrade over successive compactions. In a long-running session, the conversation gets compacted multiple times. Each compaction produces a summary, and the next compaction merges that summary with new messages. After 3+ compactions, do facts from the first compaction still survive?

This is the merge-of-merge problem. Scenario 01 tests a single merge (2 phases). This scenario tests 3 phases — the summary from phase 1 feeds into phase 2, which feeds into phase 3.

## Conversation

### Phase 1: Initial apartment search

```
system: You are a helpful AI assistant with browser tools.

user: Help me find a 2-bedroom apartment in Denver under $2000/month. I need pet-friendly and in-unit laundry.

A: I'll search for apartments in Denver for you.
  [Called tools: browse_page]

tool (browse_page): [Page: Apartments.com Denver | https://www.apartments.com/denver-co/2-bedrooms/ | 200]
  [Viewport: 0-900 of 15000px]
  [h1] 2 Bedroom Apartments in Denver
  [h2] 847 Results
  [8] [link] The Retreat at Lowry — $1,650/mo · 2bd/2ba · Pet Friendly · In-Unit W/D
  [9] [link] Parkside at Stapleton — $1,875/mo · 2bd/1ba · Pet Friendly · Shared Laundry
  [10] [link] Mile High Vista — $1,920/mo · 2bd/2ba · Pet Friendly · In-Unit W/D
  [11] [link] Cherry Creek Lofts — $2,200/mo · 2bd/2ba · Pet Friendly · In-Unit W/D

A: Found several options. Let me check the top two that meet all your criteria.
  [Called tools: click]

tool (click): [Page: The Retreat at Lowry | https://www.apartments.com/the-retreat-at-lowry/denver-co/ | 200]
  [Viewport: 0-900 of 8000px]
  [h1] The Retreat at Lowry
  $1,650/mo · 2 Bed / 2 Bath · 950 sq ft
  Pet Policy: Dogs and cats welcome, $300 deposit, $25/mo pet rent
  Amenities: In-unit washer/dryer, dishwasher, central AC, balcony
  Parking: 1 reserved spot included
  Lease: 12-month minimum
  Available: April 1, 2025
  [12] [link] Schedule Tour
  [13] [link] Apply Now

A: [Called tools: click]

tool (click): [Page: Mile High Vista | https://www.apartments.com/mile-high-vista/denver-co/ | 200]
  [Viewport: 0-900 of 7500px]
  [h1] Mile High Vista
  $1,920/mo · 2 Bed / 2 Bath · 1,100 sq ft
  Pet Policy: Dogs and cats welcome, $500 deposit, $35/mo pet rent
  Amenities: In-unit washer/dryer, granite counters, walk-in closet, gym
  Parking: Underground garage, $75/mo
  Lease: 6 or 12 month
  Available: March 15, 2025
  [14] [link] Schedule Tour

A: Here are the two best options that meet all your criteria (2bd, pet-friendly, in-unit laundry, under $2000):

  **The Retreat at Lowry** — $1,650/mo
  - 2bd/2ba, 950 sq ft
  - Pets: $300 deposit + $25/mo
  - Parking included
  - Available April 1

  **Mile High Vista** — $1,920/mo
  - 2bd/2ba, 1,100 sq ft
  - Pets: $500 deposit + $35/mo
  - Parking: $75/mo extra
  - Available now

  Retreat is cheaper overall. Mile High Vista is bigger with more amenities but parking adds cost.
```

### Phase 2: Neighborhood research

```
user: What neighborhoods are those in? Which is safer?

A: Let me look up the neighborhoods.
  [Called tools: browse_page]

tool (browse_page): [Page: Denver Neighborhood Guide | https://www.niche.com/places-to-live/denver-co/ | 200]
  [Viewport: 0-900 of 10000px]
  [h1] Denver Neighborhoods
  Lowry: A- overall, A for safety, B+ for nightlife, former Air Force base, family-friendly
  Stapleton/Central Park: A overall, A+ for safety, B for nightlife, newer development
  Capitol Hill: B overall, C+ for safety, A for nightlife, walkable, younger crowd
  Five Points: B- overall, C for safety, B+ for dining, gentrifying rapidly

A: [Called tools: browse_page]

tool (browse_page): [Page: Mile High Vista Location | https://www.apartments.com/mile-high-vista/denver-co/neighborhood/ | 200]
  [Viewport: 0-900 of 5000px]
  Mile High Vista is located in the Five Points neighborhood.
  Walk Score: 82 · Transit Score: 65 · Bike Score: 90
  Nearby: restaurants, light rail station, City Park

A: Neighborhood comparison:

  **The Retreat at Lowry** — Lowry neighborhood
  - Safety: A rating (one of Denver's safest)
  - Vibe: Family-friendly, former Air Force base, quieter
  - Walkability: moderate

  **Mile High Vista** — Five Points neighborhood
  - Safety: C rating (gentrifying, more incidents)
  - Vibe: Trendy, great dining, younger crowd
  - Walk Score: 82, near light rail

  For safety, Lowry (Retreat) is significantly better. Five Points (Mile High Vista) has better walkability and dining but lower safety ratings.

user: I'm leaning toward the Retreat. Can you check the reviews?
```

### Phase 3: Reviews and application

```
A: [Called tools: browse_page]

tool (browse_page): [Page: Retreat at Lowry Reviews | https://www.apartments.com/the-retreat-at-lowry/denver-co/reviews/ | 200]
  [Viewport: 0-900 of 6000px]
  [h1] Reviews for The Retreat at Lowry
  Overall: 4.2/5 (87 reviews)
  [h3] ★★★★★ Love this place
  By ResidentSarah on Feb 2025
  Quiet, well-maintained, management is responsive. The dog park is great.
  [h3] ★★★★ Good value
  By DenverNative on Jan 2025
  Affordable for the area. Only complaint: thin walls between units.
  [h3] ★★★ Parking issues
  By FrustratedTenant on Dec 2024
  The included parking spot is in an open lot. It gets icy in winter and they don't always salt it.
  [h3] ★★★★★ Best apartment I've had
  By PetOwnerMike on Nov 2024
  Staff is pet-friendly for real, not just on paper. Dog park, pet washing station.

A: Reviews for The Retreat at Lowry (4.2/5, 87 reviews):

  **Positives**: Quiet, well-maintained, responsive management, great dog park and pet amenities, good value for the area.

  **Concerns**:
  - Thin walls between units (noise from neighbors)
  - Open parking lot gets icy in winter, inconsistent salting

  Overall very positive. The pet amenities are a highlight. Want me to help you start the application?

user: Yes, what do I need to apply?

A: [Called tools: click]

tool (click): [Page: Apply - Retreat at Lowry | https://www.apartments.com/the-retreat-at-lowry/denver-co/apply/ | 200]
  [Viewport: 0-900 of 4000px]
  [h1] Application for The Retreat at Lowry
  Application fee: $50 per applicant
  Required documents:
  - Government-issued photo ID
  - Proof of income (last 3 pay stubs or tax return)
  - Rental history (last 2 years)
  - Pet vaccination records
  Income requirement: 3x monthly rent ($4,950/mo gross income)

A: To apply for The Retreat at Lowry, you'll need:

  - **Application fee**: $50 per applicant
  - **Documents**: Photo ID, last 3 pay stubs, 2 years rental history, pet vaccination records
  - **Income requirement**: $4,950/mo gross (3x rent of $1,650)
  - **Available move-in**: April 1, 2025

  Want me to start filling out the application?

user: Not yet, let me gather the documents first. Can you save all this info somewhere so I don't lose it?
```

## Required Facts

### From Phase 1 (must survive all compactions)

| Fact | Anchored pattern |
|------|-----------------|
| Retreat at Lowry apartment | `r"[Rr]etreat.*[Ll]owry"` |
| Retreat price $1650 | `r"\$?1,?650"` |
| Retreat 2bd/2ba 950 sqft | `r"950"` |
| Retreat pet deposit $300 | `r"\$?300.*deposit|deposit.*\$?300"` |
| Mile High Vista apartment | `r"[Mm]ile [Hh]igh [Vv]ista"` |
| Mile High Vista price $1920 | `r"\$?1,?920"` |
| Denver location | `r"[Dd]enver"` |
| Pet-friendly requirement | `r"[Pp]et"` |
| In-unit laundry requirement | `r"laundry|washer|W/D"` |

### From Phase 2 (must survive 2 compactions)

| Fact | Anchored pattern |
|------|-----------------|
| Lowry neighborhood safety A | `r"[Ll]owry.*safe|safe.*[Ll]owry|[Ll]owry.*A"` |
| Five Points safety C | `r"[Ff]ive [Pp]oints.*C|C.*safe.*[Ff]ive"` |
| User leaning toward Retreat | `r"[Rr]etreat|lean|prefer"` |

### From Phase 3 (must survive 1 compaction)

| Fact | Anchored pattern |
|------|-----------------|
| Retreat review score 4.2 | `r"4\.2"` |
| Thin walls concern | `r"thin.*wall|wall.*thin|noise"` |
| Application fee $50 | `r"\$?50.*fee|fee.*\$?50|application.*\$?50"` |
| Income requirement $4950 | `r"\$?4,?950|3x.*rent"` |
| Available April 1 | `r"[Aa]pril"` |

## Probes

Tests whether facts from all 3 phases survive the final compaction. The key risk is Phase 1 data (apartment details) degrading through successive merges while Phase 3 data (reviews, application) stays fresh.

- **Probe 1** (anti-loop): The agent already found and compared apartments. If Phase 1 data is lost, it would re-search apartments.com from scratch.
- **Probe 2** (Phase 1 survival): The specific apartment details ($1650, 950 sqft) were found in Phase 1. After 2 more compactions, do the numbers survive?
- **Probe 3** (cross-phase synthesis): The user chose the Retreat based on safety (Phase 2) and reviews (Phase 3). The agent needs to know WHY it was chosen.
- **Probe 4** (forward action): The user wants to gather documents before applying. The agent should know what documents are needed without re-checking.

| Question | Pass pattern | Fail pattern |
|----------|-------------|-------------|
| Have you already found apartments, or do you need to search? | `r"already|found|Retreat|Mile High|two|2"` | `r"need to search|should search|haven.t"` |
| What is the monthly rent and size of The Retreat at Lowry? | `r"1,?650.*950|950.*1,?650"` | — |
| Why did the user choose The Retreat over Mile High Vista? | `r"safe|Lowry|A.*rating|quiet|family"` | — |
| What documents does the user need to gather for the application? | `r"pay stub|ID|photo|rental history|pet.*vaccin"` | `r"check.*application|look up|need to find"` |
