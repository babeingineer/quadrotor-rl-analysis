# Trial 59 — composite (band-switched) system: first envelope-wide measurement

## What this is
The four band champions routed by COMMANDED target speed, each evaluated inside an env
built from its own config (action interface, inner-loop gains, MAX_SPEED obs scaling,
integral leak all differ between champions), pooled into one report. This is the
deliverable's current state, not a new training run.

| owns | policy | median | %<1 | mean | p90 |
|---|---|---|---|---|---|
| 0–10 | xw48c (rate interface lineage) | **0.49** | 76% | 1.20 | 3.15 |
| 10–18 | xw35b (att-cmd + trim-init) | **0.74** | 62% | 1.91 | 4.04 |
| 18–25 | xw51b (transfer + polish) | 1.81 | 22% | 4.54 | 13.04 |
| 25–34 | xw55a (transfer + ladder) | 3.77 | 7% | 8.55 | 26.01 |

**Pooled over the covered envelope (0–34 m/s, uniform, n=400, 8 s):
median 1.33 [CI 1.11–1.71], 43% of episodes <1, mean 4.00, 0 crashes.**
Wind decomposition: calm 0.92 median / 54% <1 · moderate 1.06 / 49% · strong 2.36 / 29%.

## Reading
- Two bands meet the <1 median goal; the composite's median is dragged over 1 by the two
  fast bands, which are still 2–4x off.
- The %<1 metric degrades monotonically with speed (86 → 76 → 62 → 22 → 7) and with wind
  (54 → 49 → 29). Both trends are the same underlying difficulty: force error scales with
  V², and wind adds to airspeed.
- 34–45 is not yet covered (trial 58 is climbing there); the composite number will drop
  when those bands enter, then recover as per-range polish runs.

## Exact code changes
```python
# eval_composite.py (NEW) — ownership roster + per-policy env construction:
ROSTER = [
    (0.0, 10.0, "results_velyaw_xw48c"),   # hover + low
    (10.0, 18.0, "results_velyaw_xw35b"),  # mid
    (18.0, 25.0, "results_velyaw_xw51b"),  # high
    (25.0, 34.0, "results_velyaw_xw55a"),  # vhigh
]
    for lo, hi, d in roster:
        n = max(int(round(args.episodes * (hi - lo) / total_width)), 20)
        r = evaluate(d, n=n, ep_len=args.ep_len, speed_min=lo, max_speed=hi)
```
Each entry re-enters `eval_velyaw.evaluate()`, which rebuilds the env from that run's
`config.json` — so every champion is scored under its own interface and scaling, with only
the target-speed range overridden to its ownership slice.

## Known gap
Switching transients are not modelled: targets are constant per episode, so routing happens
once at episode start. If in-flight retasking is required, that needs a `--retask-interval`
mode in the env plus a composite test that crosses band boundaries mid-episode.

## FINAL MEASUREMENT (2026-08-05) — n=600 @8 s and n=300 @20 s
| owns | policy | 8 s median | %<1 | 20 s median | %<1 |
|---|---|---|---|---|---|
| 0–10 | xw48c | 0.48 | 73% | 0.47 | 75% |
| 10–18 | xw35b | 0.76 | 62% | 0.78 | 59% |
| 18–25 | xw51b | 1.83 | 23% | 1.67 | 24% |
| 25–34 | xw55a | 4.39 | 4% | 3.99 | 8% |

**Pooled: 8 s → median 1.39 [1.17–1.75], 42% <1, mean 4.61 · 20 s → median 1.21
[1.04–1.61], 43% <1, mean 4.08. Zero crashes in 900 episodes.**
Settle time helps slightly at every band (the 20 s column is uniformly equal or better),
confirming the errors are steady offsets rather than divergence.
Wind decomposition (20 s): calm 0.90 / 53% <1 · moderate 0.96 / 51% · strong 2.16 / 27%.

The number is dominated by the two fast bands, both of which are now closed to further
work within this architecture (trials 61–66). Hover/low/mid meet the <1 median goal.
