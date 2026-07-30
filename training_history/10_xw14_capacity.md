# Trial 10 — LOOP iter 4: capacity probe (512×512 net)

| | |
|---|---|
| run dir | `results_velyaw_xw14` (FRESH) |
| date | 2026-07-29 |
| loop goal | velocity error **< 1 m/s** |
| baseline | xw13: **6.70 m/s / 4.1°** (best); floor ~6.7 replicated across 3 independent lineages |
| changes | **net_arch [256,256] → [512,512]** — everything else identical to trial 09 |
| status | **IN PROGRESS** — auto-analyzed + auto-logged on completion |

## Hypothesis (iteration 4)
Three independently-trained policies converge to the same band-wise error pattern
(low ~3.4 / mid ~6.7 / high ~11.6). Two remaining explanations: (a) environment floor
(0–20 m/s wind × S=C=b=1 aero × DR), or (b) **policy capacity** — this aero is far more
nonlinear than anything the [256,256] net has solved before (the tailsitter's "deeper didn't
help" lesson was measured on much simpler flat-plate physics, so it may not transfer).
This run isolates (b). If it lands at ~6.7 again, (a) is confirmed by elimination and the
user's physics answers (real S/C/b, wind spec) become the gating factor.

## Exact changes
**No code changes** — `--net 512,512` flag (existing):
```bash
python train.py --xwing-aero --yaw-bias 0.3 --max-speed 25 \
                --yaw-gate --yaw-att-gate --vel-precision 0.7 --ent-coef 0.003 \
                --net 512,512 --n-envs 10 --timesteps 12000000 --device cpu \
                --out-dir results_velyaw_xw14
# auto: analyze_velyaw.py --dir results_velyaw_xw14 && log_trial.py
```

## Decision criteria
- < 1.0 → SUCCESS.
- ≤ ~5.5 → capacity was binding: iterate on size/steps (768 wide / 20M).
- ≈ 6.7 → **environmental floor confirmed by elimination** → report to user with full
  evidence; proceeding needs real S/C/b and/or the 0–15 wind spec (or acceptance of a
  revised target under current physics).

---

## OUTCOME: INTERRUPTED — inconclusive
The Claude Code session hosting the run was torn down at ~2.55M/12M steps; no final model or
analysis was produced. The capacity question (512×512) is folded into trial 11, which also
applies the newly-confirmed real spec (wind 0–15 m/s; S=C=b=1 confirmed real by the user —
the "over-aeroed" hypothesis is retired).
