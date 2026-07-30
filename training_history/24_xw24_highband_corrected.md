# Trial 24 — xw24: HIGH band (18–25 m/s) with the corrected recipe

## Why
The high band is the last open frontier (best RL: 8.94 with stiff gains; classical ceiling:
median 3.90, 26% < 1). Two findings make this the decisive experiment:

1. **No physics obstruction** (trial 21, addenda 4+5): fine trim optimization proves an exact
   force balance exists for **100% of high-band draws**, including the absolute worst corner
   (25 m/s target + 15 m/s directly adverse wind = Va 40, heaviest mass, ±20% extreme aero
   draws — all residual 0.000 m/s²). At trim, drag is only tens of N vs 440 N thrust.
2. **The classical cascade fails for a structural reason RL doesn't share**: its residual is a
   saturated-integrator constant offset trapped in an authority/windup dilemma (clamp 8→8.4,
   20→11.4, 40→25.0, 80→38.4; anti-windup also fails) caused by the attitude→aero→F_des→attitude
   coupling loop. A policy that learns the coupled mapping directly has no such dilemma.

Every prior high-band RL attempt (xw19/xw20/xw21) trained WITHOUT the two ingredients the
low-band work proved essential: a TRUE integrator (leak τ=3 s bounds steady error) and
episodes long enough to reward settling (10 s protocol clipped scores; classical went
1.48→0.65 median given 20 s). xw24 is therefore the first *fair* RL test at the high band.

## What (vs xw19/xw20)
- `--integral-tau 1e6` (TRUE integrator; was leaky τ=3)
- `--episode-len 20` in train + continuation + eval (was 8–10 s)
- stiff inner loop `--kp-rate 40,40,25 --ki-rate 10,10,5` (kept from xw20: ripple ~1 m/s)
- `--gamma 0.999` (horizon must span the settle time)
- otherwise the validated stack: yaw gate + attitude gate, precision 0.7, cov width 5,
  ent 0.003, wind 0–15, aero DR ON (xw21 proved no-DR is WORSE: 11.40 vs 8.94)

## Command (auto chain, queued by scheduler.sh after xw22b/xw23)
```bash
python train.py --xwing-aero --yaw-bias 0.3 --max-speed 25 --speed-min 18 --wind-max 15 \
    --yaw-gate --yaw-att-gate --vel-precision 0.7 --cov-width 5 --ent-coef 0.003 \
    --gamma 0.999 --episode-len 20 --integral-tau 1e6 --kp-rate 40,40,25 --ki-rate 10,10,5 \
    --n-envs 6 --timesteps 8000000 --device cpu --out-dir results_velyaw_xw24 \
&& continue +4M @1e-4 (episode-len 20) && analyze (ep_len 20) && log_trial
```
No new code for this trial itself; it runs on the VecNormSaveCallback-fixed train.py /
continue_train.py (exact code in [22_xw22_true_integrator.md](22_xw22_true_integrator.md),
CRASH + RELAUNCH section).

## Pre-registered criteria (20 s eval protocol, high band, 100 eps)
- **SUCCESS**: median < 1 m/s (matches what classical achieves on favorable draws, on the
  typical draw) — then push mean < 1 via convergence/continuation.
- **PROGRESS**: median 1–3 or mean ≤ 5 — corrected recipe helps; iterate (longer episodes,
  reward shaping at high Q, or band-split 18–21/21–25).
- **FAILURE**: mean ≥ 8.9 (no better than xw20) — the recipe's gains don't transfer to high Q;
  next lever is architecture (elevon-led control / LSTM verdict from lstm3).

## Result
*(auto-appended by log_trial.py when the chain lands)*

## PRE-START NOTES
- 2026-07-31 00:10: a scheduler race (process-poll fired before the xw22b resume spawned)
  launched this run prematurely alongside 2 other chains; killed at ~15 min, dir cleaned,
  scheduler rewritten (sequential queue). No results were produced or used.
- 2026-07-31 00:5x: **recipe revised γ 0.999 → 0.997** (same reasoning as trial 23: xw22b
  showed γ 0.999 regresses + collapses yaw; 0.997 is the empirical best-velocity-at-speed
  anchor from xw17). Command block above still accurate otherwise.
