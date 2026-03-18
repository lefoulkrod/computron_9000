# Scenario 11: Long-Running Data Gathering

## Purpose

Stress test for chunked summarization. The agent visits 10+ sources, gathering structured data from each. Tests whether all data points survive when spread across multiple chunks, and whether the merge step correctly combines data from different sources without dropping any.

## Conversation

Agent compares laptop specs across multiple review sites for the user.

```
system: You are a helpful AI assistant with browser tools.

user: I'm buying a laptop for machine learning work. Budget is $2000-3000. I need at least 32GB RAM and a good GPU. Compare options from at least 5 different sources and give me a recommendation.

A: I'll research ML laptops across multiple sources. Starting with Notebookcheck.
  [Called tools: browse_page]

tool (browse_page): [Page: Notebookcheck Best ML Laptops | https://www.notebookcheck.net/best-ml-laptops-2025 | 200]
  [Viewport: 0-900 of 12000px]
  [h1] Best Laptops for Machine Learning 2025
  1. Lenovo ThinkPad P16s Gen 3 — RTX 4070, 32GB, $2,199 — Editor's Choice
  2. ASUS ProArt Studiobook 16 — RTX 4060, 64GB, $2,499 — Best Value
  3. Dell Precision 5690 — RTX 5000 Ada, 64GB, $3,199 — Best Performance (over budget)

A: Good start. Let me check Tom's Hardware.
  [Called tools: browse_page]

tool (browse_page): [Page: Tom's Hardware Laptop Reviews | https://www.tomshardware.com/best-picks/best-ml-laptops | 200]
  [Viewport: 0-900 of 10000px]
  [h1] Best Laptops for Machine Learning
  1. ASUS ROG Zephyrus G16 — RTX 4070, 32GB, $2,299 — Top Pick
  2. Lenovo Legion Pro 7i — RTX 4080, 32GB, $2,799 — Best GPU
  3. MSI Creator Z17 — RTX 4070, 64GB, $2,599 — Best Display

A: Now RTings.
  [Called tools: browse_page]

tool (browse_page): [Page: RTings Best Laptops for ML | https://www.rtings.com/laptop/reviews/best/machine-learning | 200]
  [Viewport: 0-900 of 9000px]
  [h1] Best Laptops for Machine Learning
  1. Lenovo ThinkPad P16s Gen 3 — Score 8.4/10 — "Excellent thermal management"
  2. Apple MacBook Pro 16 M3 Max — Score 8.7/10 — "Best unified memory, but limited CUDA support"
  3. ASUS ROG Zephyrus G16 — Score 8.2/10 — "Great gaming GPU doubles for ML"

A: Let me check YouTube reviews for hands-on opinions.
  [Called tools: browse_page]

tool (browse_page): [Page: YouTube Search: ML Laptop 2025 | https://www.youtube.com/results?search_query=best+ml+laptop+2025 | 200]
  [Viewport: 0-900 of 8000px]
  [h2] Search Results
  [15] [link] "Best ML Laptops 2025 - Dave Lee" — 1.2M views
  [16] [link] "I Tested 5 ML Laptops - Linus Tech Tips" — 890K views
  [17] [link] "ThinkPad P16s vs ROG Zephyrus for ML - JarrodsTech" — 450K views

A: [Called tools: click]

tool (click): [Page: Dave Lee ML Laptops 2025 | https://www.youtube.com/watch?v=abc123 | 200]
  [Viewport: 0-900 of 5000px]
  Video description:
  My top picks for ML work in 2025:
  1. Lenovo ThinkPad P16s Gen 3 — "Best overall for the price"
  2. ASUS ROG Zephyrus G16 — "Best if you also game"
  3. Razer Blade 16 — RTX 4070, 32GB, $2,699 — "Premium build quality"
  Key insight: The ThinkPad P16s has certified GPU drivers for ML frameworks, which matters more than raw GPU speed for stability.

A: Now let me check Amazon for actual current prices.
  [Called tools: browse_page]

tool (browse_page): [Page: Amazon ML Laptops | https://www.amazon.com/s?k=machine+learning+laptop+32gb | 200]
  [Viewport: 0-900 of 15000px]
  [h2] Results
  Lenovo ThinkPad P16s Gen 3 — $2,149 (was $2,199, 2% off)
  ASUS ROG Zephyrus G16 — $2,199 (was $2,299, 4% off)
  Lenovo Legion Pro 7i — $2,649 (was $2,799, 5% off)
  MSI Creator Z17 — $2,449 (was $2,599, 6% off)
  Razer Blade 16 — $2,599 (was $2,699, 4% off)

A: Let me also check the Lenovo and ASUS official sites for any direct deals.
  [Called tools: browse_page]

tool (browse_page): [Page: Lenovo ThinkPad P16s | https://www.lenovo.com/us/en/p/laptops/thinkpad/thinkpadp/thinkpad-p16s-gen3/ | 200]
  [Viewport: 0-900 of 8000px]
  [h1] ThinkPad P16s Gen 3
  Starting at $1,999 with student discount
  Configurable: up to 64GB RAM, RTX 4070
  ISV certified for: PyTorch, TensorFlow, CUDA 12
  3-year warranty included
  Free shipping

A: [Called tools: browse_page]

tool (browse_page): [Page: ASUS ROG Zephyrus G16 | https://www.asus.com/laptops/rog-zephyrus-g16/ | 200]
  [Viewport: 0-900 of 9000px]
  [h1] ROG Zephyrus G16
  $2,299.99 direct
  NVIDIA GeForce RTX 4070 8GB
  32GB DDR5-5600
  1TB PCIe 4.0 NVMe
  16" 2560x1600 240Hz OLED
  Battery: up to 10 hours
  Weight: 4.4 lbs

A: Now let me check Reddit for real user experiences.
  [Called tools: browse_page]

tool (browse_page): [Page: Reddit r/MachineLearning | https://www.reddit.com/r/MachineLearning/comments/best_laptop_2025/ | 200]
  [Viewport: 0-900 of 7000px]
  [h1] Best laptop for ML in 2025?
  Top comment (342 upvotes): "ThinkPad P16s. The ISV certification means your CUDA environment just works. I wasted weeks debugging driver issues on my ROG."
  Second comment (187 upvotes): "If you can stretch to $3k, the Legion Pro 7i with 4080 is a beast. 30% faster training than 4070."
  Third comment (156 upvotes): "Skip the MacBook for ML. No CUDA support means you'll be fighting compatibility issues with every library."
  Fourth comment (89 upvotes): "ROG Zephyrus is amazing but runs HOT during training. Get a cooling pad."

A: Let me check one more source — Puget Systems, they do actual ML benchmarks.
  [Called tools: browse_page]

tool (browse_page): [Page: Puget Systems ML Benchmarks | https://www.pugetsystems.com/labs/articles/laptop-ml-benchmarks-2025/ | 200]
  [Viewport: 0-900 of 10000px]
  [h1] Laptop ML Performance Benchmarks 2025
  [h2] PyTorch Training (ResNet-50, ImageNet subset)
  ThinkPad P16s (RTX 4070): 45 min — baseline
  ROG Zephyrus G16 (RTX 4070): 43 min — 4% faster (better cooling)
  Legion Pro 7i (RTX 4080): 32 min — 29% faster
  MacBook Pro M3 Max: 58 min — 29% slower (no CUDA, using MPS)
  [h2] Inference (BERT-large)
  ThinkPad P16s: 12ms/sample
  ROG Zephyrus: 11ms/sample
  Legion Pro 7i: 8ms/sample

A: Here's my comprehensive comparison from 8 sources:

  **Top Recommendation: Lenovo ThinkPad P16s Gen 3**
  - Price: $2,149 (Amazon) / $1,999 (Lenovo direct with student discount)
  - GPU: RTX 4070, ISV certified for PyTorch/TensorFlow/CUDA 12
  - RAM: 32GB (configurable to 64GB)
  - Reviews: Notebookcheck Editor's Choice, RTings 8.4/10, Dave Lee's #1 pick, Reddit top choice
  - Benchmarks: 45 min ResNet-50 training, solid thermals
  - Why: ISV certification means ML frameworks work without driver headaches

  **Runner-up: ASUS ROG Zephyrus G16**
  - Price: $2,199 (Amazon) / $2,299 (ASUS direct)
  - GPU: RTX 4070 8GB
  - RAM: 32GB DDR5-5600
  - Display: 16" OLED 240Hz (best display in class)
  - Reviews: Tom's Hardware Top Pick, RTings 8.2/10
  - Benchmarks: 43 min ResNet-50 (slightly faster than ThinkPad)
  - Caveat: Runs hot during training, needs cooling pad

  **Best Performance (stretch budget): Lenovo Legion Pro 7i**
  - Price: $2,649 (Amazon)
  - GPU: RTX 4080 — 29% faster training
  - Benchmarks: 32 min ResNet-50
  - Worth it if training time matters

  **Avoid for ML: Apple MacBook Pro M3 Max**
  - No CUDA support, 29% slower in benchmarks, compatibility issues with ML libraries

user: I think I'll go with the ThinkPad. Can you find out if there are any coupon codes for Lenovo right now?
```

## Required Facts

| Fact | Anchored pattern |
|------|-----------------|
| ThinkPad P16s recommended | `r"[Tt]hink[Pp]ad.*P16"` |
| ThinkPad price $2149 Amazon | `r"\$?2,?149"` |
| ThinkPad price $1999 Lenovo | `r"\$?1,?999"` |
| RTX 4070 GPU | `r"RTX\s*4070"` |
| ISV certified | `r"ISV|certified"` |
| ROG Zephyrus runner up | `r"[Zz]ephyrus.*runner|runner.*[Zz]ephyrus|[Zz]ephyrus.*second|second.*[Zz]ephyrus"` |
| ROG runs hot | `r"hot|thermal|cooling pad"` |
| Legion Pro 7i stretch option | `r"[Ll]egion.*Pro.*7i"` |
| Legion RTX 4080 29% faster | `r"RTX\s*4080|29%"` |
| MacBook avoid for ML | `r"[Mm]ac[Bb]ook.*avoid|avoid.*[Mm]ac|no.*CUDA|skip.*[Mm]ac"` |
| Notebookcheck source | `r"[Nn]otebookcheck"` |
| RTings score 8.4 | `r"8\.4"` |
| Puget Systems benchmarks | `r"[Pp]uget"` |
| Reddit user feedback | `r"[Rr]eddit"` |
| Budget $2000-3000 | `r"2,?000.*3,?000|budget"` |

## Probes

The agent visited 8 sources and synthesized data from all of them. The risk is that chunked summarization splits the sources across chunks and the merge step drops data from some sources while keeping others.

- **Probe 1** (forward action): User chose ThinkPad and wants coupon codes. Agent should search for Lenovo coupons, not re-research laptops.
- **Probe 2** (anti-loop): The agent already compared 5+ laptops across 8 sources. Re-researching would waste 10+ minutes.
- **Probe 3** (synthesis survival): The recommendation was based on cross-referencing multiple sources (ISV cert from Lenovo, benchmarks from Puget, user feedback from Reddit). All need to survive.
- **Probe 4** (negative recommendation): The agent determined MacBook is bad for ML. If this is lost, the user might ask about MacBook and get a wrong recommendation.

| Question | Pass pattern | Fail pattern |
|----------|-------------|-------------|
| What should you do next? | `r"coupon|discount|deal|promo|Lenovo"` | `r"research.*laptop|compare.*laptop|find.*laptop"` |
| Have you already compared laptop options, or do you need to research? | `r"already|compared|found|ThinkPad|Zephyrus|Legion"` | `r"need to research|should search|haven.t"` |
| Why did you recommend the ThinkPad P16s over the ROG Zephyrus? | `r"ISV|certif|driver|stable|CUDA.*works"` | — |
| Would a MacBook Pro be good for ML work? | `r"no|avoid|skip|no.*CUDA|not recommend|poor|slower|wouldn.t"` | — |
