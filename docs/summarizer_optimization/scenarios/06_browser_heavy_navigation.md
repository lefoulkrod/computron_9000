# Scenario 06: Browser Heavy Navigation

## Purpose

Tests that the summarizer handles conversations with many intermediate navigation URLs. Real browser sessions visit 15+ pages but only a handful matter for results. The summarizer should preserve result URLs and data while dropping search pages, category listings, and filter pages.

## Agent Type

BROWSER_AGENT

## Conversation

Agent researches and compares health insurance plans across multiple sites. Lots of navigation with dead ends, search pages, and category listings mixed with actual plan detail pages.

```
system: You are a helpful AI assistant with browser tools.

user: I need to compare health insurance plans for a family of 4 in Austin, TX. Budget is around $800/month. Find me at least 3 options with deductibles and copay info.

A: I'll research health insurance plans for you. Let me start with healthcare.gov.
  [Called tools: browse_page]

tool (browse_page): [Page: HealthCare.gov | https://www.healthcare.gov | 200]
  [Viewport: 0-900 of 3000px]
  [1] [searchbox] Search
  [2] [link] See Plans & Prices
  [3] [link] Get Coverage
  [4] [link] Keep or Update Your Plan

A: [Called tools: click]

tool (click): [Page: See Plans | https://www.healthcare.gov/see-plans/ | 200]
  [Viewport: 0-900 of 4000px]
  [h1] See Health Plans & Prices
  [5] [textbox] ZIP Code
  [6] [combobox] State = "Select"
  [7] [textbox] Household Size
  [8] [textbox] Estimated Income

A: [Called tools: fill_field, fill_field, fill_field, select_option, click]

tool (fill_field): [5] [textbox] ZIP Code = "78701"
tool (fill_field): [7] [textbox] Household Size = "4"
tool (fill_field): [8] [textbox] Estimated Income = "$95,000"
tool (select_option): [6] [combobox] State = "Texas"
tool (click): [Page: Plans for 78701 | https://www.healthcare.gov/see-plans/results/?zip=78701&state=TX&size=4&income=95000 | 200]
  [Viewport: 0-900 of 18000px]
  [h1] 23 Plans Available
  [h2] Filter By
  [10] [combobox] Metal Level = "All"
  [11] [combobox] Plan Type = "All"
  [12] [combobox] Deductible Range = "All"
  [h2] Results
  [13] [link] Blue Cross Blue Shield Silver 3000 — $724/mo · Deductible: $3,000 · Copay: $35
  [14] [link] Oscar Health Silver Select — $689/mo · Deductible: $2,500 · Copay: $30
  [15] [link] Ambetter Essential Care Silver — $651/mo · Deductible: $4,000 · Copay: $40
  [16] [link] Molina Marketplace Silver — $612/mo · Deductible: $3,500 · Copay: $25
  [17] [link] BCBS Gold 1500 — $892/mo · Deductible: $1,500 · Copay: $25
  [18] [link] Oscar Health Gold Plus — $934/mo · Deductible: $1,000 · Copay: $20

A: Found 23 plans. Several Silver plans are within budget. Let me check the top options in detail. Starting with Oscar Health.
  [Called tools: click]

tool (click): [Page: Oscar Health Silver Select | https://www.healthcare.gov/see-plans/plan/oscar-health-silver-select-78701/?year=2025 | 200]
  [Viewport: 0-900 of 12000px]
  [h1] Oscar Health Silver Select
  Monthly Premium: $689/mo (family of 4)
  Annual Deductible: $2,500/person, $5,000/family
  Out-of-Pocket Maximum: $8,700/person, $17,400/family
  [h2] Copays & Coinsurance
  Primary Care: $30 copay
  Specialist: $65 copay
  Urgent Care: $75 copay
  Emergency Room: $350 copay after deductible
  Generic Drugs: $15 copay
  Preferred Brand Drugs: $50 copay
  [h2] Network
  Network Type: EPO
  Includes: Seton Medical Center, Austin Regional Clinic
  [19] [link] Full provider directory
  [20] [link] Summary of Benefits
  [21] [link] Back to results

A: Good details. Let me check Molina — it's the cheapest.
  [Called tools: click]

tool (click): [Page: Plans for 78701 | https://www.healthcare.gov/see-plans/results/?zip=78701&state=TX&size=4&income=95000 | 200]
  [Viewport: 0-900 of 18000px]
  [h1] 23 Plans Available
  [13] [link] Blue Cross Blue Shield Silver 3000 — $724/mo
  [14] [link] Oscar Health Silver Select — $689/mo
  [15] [link] Ambetter Essential Care Silver — $651/mo
  [16] [link] Molina Marketplace Silver — $612/mo

A: [Called tools: click]

tool (click): [Page: Molina Marketplace Silver | https://www.healthcare.gov/see-plans/plan/molina-marketplace-silver-78701/?year=2025 | 200]
  [Viewport: 0-900 of 11000px]
  [h1] Molina Marketplace Silver
  Monthly Premium: $612/mo (family of 4)
  Annual Deductible: $3,500/person, $7,000/family
  Out-of-Pocket Maximum: $9,100/person, $18,200/family
  [h2] Copays & Coinsurance
  Primary Care: $25 copay
  Specialist: $70 copay
  Urgent Care: $50 copay
  Emergency Room: $400 copay after deductible
  Generic Drugs: $10 copay
  Preferred Brand Drugs: $60 copay
  [h2] Network
  Network Type: HMO
  Includes: CommUnityCare, Lone Star Circle of Care
  [22] [link] Full provider directory
  [23] [link] Summary of Benefits

A: Now let me also check reviews. Let me search for Molina reviews in Texas.
  [Called tools: browse_page]

tool (browse_page): [Page: Google Search | https://www.google.com/search?q=molina+marketplace+texas+reviews+2025 | 200]
  [Viewport: 0-900 of 8000px]
  [h2] Search Results
  [24] [link] Molina Healthcare Reviews 2025 - NerdWallet
  [25] [link] Molina Texas Plans Rated - InsureHealth.com
  [26] [link] Worst Health Insurance Companies 2025 - Reddit
  [27] [link] Molina Provider Network Austin TX - molina.com

A: [Called tools: click]

tool (click): [Page: Molina Reviews | https://www.nerdwallet.com/article/health/molina-healthcare-review | 200]
  [Viewport: 0-900 of 9000px]
  [h1] Molina Healthcare Review 2025
  Overall Rating: 3.2/5
  [h2] Pros
  - Lowest premiums in most markets
  - Low copays for primary care
  - Good generic drug coverage
  [h2] Cons
  - Narrow provider network — many specialists out of network
  - Prior authorization required for many services
  - Customer service rated below average (2.5/5)
  - Claims processing can be slow

A: The reviews raise concerns about Molina's network. Let me check the BCBS plan as a mid-range option.
  [Called tools: go_back, go_back]

tool (go_back): [Page: Google Search | https://www.google.com/search?q=molina+marketplace+texas+reviews+2025 | 200]
tool (go_back): [Page: Plans for 78701 | https://www.healthcare.gov/see-plans/results/?zip=78701&state=TX&size=4&income=95000 | 200]

A: [Called tools: click]

tool (click): [Page: BCBS Silver 3000 | https://www.healthcare.gov/see-plans/plan/bcbs-silver-3000-78701/?year=2025 | 200]
  [Viewport: 0-900 of 12000px]
  [h1] Blue Cross Blue Shield Silver 3000
  Monthly Premium: $724/mo (family of 4)
  Annual Deductible: $3,000/person, $6,000/family
  Out-of-Pocket Maximum: $8,500/person, $17,000/family
  [h2] Copays & Coinsurance
  Primary Care: $35 copay
  Specialist: $60 copay
  Urgent Care: $65 copay
  Emergency Room: $300 copay after deductible
  Generic Drugs: $15 copay
  Preferred Brand Drugs: $45 copay
  [h2] Network
  Network Type: PPO
  Includes: All major Austin hospitals, St. David's, Dell Medical
  [28] [link] Full provider directory
  [29] [link] Summary of Benefits

A: Now let me check Oscar reviews too for comparison.
  [Called tools: browse_page]

tool (browse_page): [Page: Google Search | https://www.google.com/search?q=oscar+health+texas+reviews+2025 | 200]
  [Viewport: 0-900 of 8000px]
  [24] [link] Oscar Health Insurance Review 2025 - NerdWallet
  [25] [link] Oscar Health vs Traditional Insurers - Forbes

A: [Called tools: click]

tool (click): [Page: Oscar Health Review | https://www.nerdwallet.com/article/health/oscar-health-review | 200]
  [Viewport: 0-900 of 8500px]
  [h1] Oscar Health Review 2025
  Overall Rating: 4.1/5
  [h2] Pros
  - Easy-to-use app and virtual care
  - $0 telehealth visits
  - Transparent pricing
  - Good preventive care coverage
  [h2] Cons
  - EPO network — no out-of-network coverage
  - Limited to urban areas
  - Higher specialist copays than some competitors

A: Here's my comparison of the 3 best options within your $800/month budget:

  **Oscar Health Silver Select** — $689/mo
  - Deductible: $2,500/$5,000 family | OOP Max: $8,700/$17,400
  - Copays: PCP $30, Specialist $65, ER $350
  - Network: EPO (Seton, Austin Regional)
  - Rating: 4.1/5 — great app, $0 telehealth, no out-of-network coverage
  - Best for: Tech-savvy families who want convenience

  **Blue Cross Blue Shield Silver 3000** — $724/mo
  - Deductible: $3,000/$6,000 family | OOP Max: $8,500/$17,000
  - Copays: PCP $35, Specialist $60, ER $300
  - Network: PPO (all major Austin hospitals, St. David's, Dell Medical)
  - Best for: Families wanting widest provider choice

  **Molina Marketplace Silver** — $612/mo (cheapest)
  - Deductible: $3,500/$7,000 family | OOP Max: $9,100/$18,200
  - Copays: PCP $25, Specialist $70, ER $400
  - Network: HMO (CommUnityCare, Lone Star)
  - Rating: 3.2/5 — cheapest but narrow network, slow claims
  - Best for: Healthy families wanting lowest premium, OK with limited network

  My recommendation: Oscar Health is the best balance of cost and quality. BCBS if you need the PPO flexibility.

user: Can you check if Dell Children's Medical Center is in Oscar's network? That's important for my kids.
```

## Compaction Boundary Analysis

With `keep_recent=6`:
- **Total messages**: 1 system + ~28 non-system
- **URLs visited**: healthcare.gov (landing), healthcare.gov/see-plans/ (form), healthcare.gov/see-plans/results/ (listing, visited 3x), 3 plan detail pages, 2 Google searches, 2 NerdWallet review pages, 2 go_back results = ~13 distinct URLs
- **Intermediate URLs**: healthcare.gov landing, /see-plans/ form, /results/ listing (3x), Google searches (2x), go_back results = 8 intermediate
- **Result URLs**: 3 plan detail pages, 2 NerdWallet reviews = 5 result URLs
- **Compacted**: Messages 2 through ~22
- **Kept**: Last 6 messages (likely the final comparison + user follow-up)

## Required Facts

| Fact | Anchored pattern |
|------|-----------------|
| Oscar Health plan | `r"[Oo]scar.*[Hh]ealth"` |
| Oscar price $689 | `r"\$?689"` |
| Oscar deductible $2500 | `r"\$?2,?500"` |
| Oscar rating 4.1 | `r"4\.1"` |
| Oscar plan URL | `r"healthcare\.gov/see-plans/plan/oscar"` |
| BCBS plan | `r"[Bb]lue\s*[Cc]ross|BCBS"` |
| BCBS price $724 | `r"\$?724"` |
| BCBS deductible $3000 | `r"\$?3,?000"` |
| BCBS network PPO | `r"PPO"` |
| BCBS plan URL | `r"healthcare\.gov/see-plans/plan/bcbs"` |
| Molina plan | `r"[Mm]olina"` |
| Molina price $612 | `r"\$?612"` |
| Molina rating 3.2 | `r"3\.2"` |
| Molina narrow network concern | `r"narrow|limited|out.of.network"` |
| NerdWallet review URL | `r"nerdwallet\.com"` |
| Austin TX location | `r"[Aa]ustin|78701"` |
| Family of 4 | `r"family.*4|4.*family"` |
| Budget $800 | `r"\$?800"` |

## Probes

The agent's biggest autonomy risks: re-searching healthcare.gov for plans (10+ minutes of navigation wasted), not knowing the user's constraints to answer the Dell Children's question, or recommending Molina without remembering the review concerns.

- **Probe 1** (forward action): The user asked about Dell Children's in Oscar's network. The agent needs to check the provider directory, not re-research plans.
- **Probe 2** (anti-loop): The agent already found 3 plans through extensive navigation. Re-searching would repeat all that work.
- **Probe 3** (anti-loop): The Molina reviews revealed serious concerns (narrow network, slow claims). If the agent lost this and recommends Molina, the user gets a bad plan.
- **Probe 4** (context): The agent needs the user's constraints to evaluate whether Dell Children's matters (it's for kids in a family of 4).

| Question | Pass pattern | Fail pattern |
|----------|-------------|-------------|
| What should you do next to answer the user's question about Dell Children's? | `r"Oscar.*network|network.*Oscar|provider.*director|check.*Dell"` | `r"search.*insurance|find.*plan|healthcare\.gov"` |
| Have you already found insurance plan options, or do you need to search? | `r"already|found|Oscar|BCBS|Molina|three|3"` | `r"need to search|should search|haven.t"` |
| What were the review concerns about the Molina plan? | `r"narrow|network|claims|customer service|3\.2|prior auth"` | — |
| What are the user's requirements for the insurance plan? | `r"family|Austin|78701|\$?800"` | — |
