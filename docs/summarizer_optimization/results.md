# Results

## Baseline (2026-03-15)

**What**: Current `_SUMMARIZE_PROMPT` + dedup + per-result cap (10k) + total budget (40k). Model: `qwen3:8b`. Probe model: `kimi-k2.5:cloud`.

7 runs total. Tests run individually due to async event loop sharing.

| Scenario | Probes | Time (range) | Length (range) | Fact Retention (range) |
|----------|--------|-------------|----------------|----------------------|
| 01_merge | 3/3 (7/7 runs) | 12.8–16.7s | 2,187–2,588 | 95–100% |
| 02_desktop | 3/3 (7/7 runs) | 4.3–8.8s | 1,253–2,069 | 64% |
| 03_browser_fail | 3/3 (6/7 runs) | 4.0–5.2s | 1,227–1,690 | 43–57% |
| 04_form_fill | 3/3 (6/7 runs) | 3.1–3.8s | 1,240–1,502 | 47% |
| 05_debug_fail | 3/3 (7/7 runs) | 3.2–6.3s | 1,015–1,787 | 67–87% |

**Probes passing**: 15/15 on 5 of 7 runs. 2 flaky runs had 1 probe failure each (03 and 04).

---

## Experiment Results
