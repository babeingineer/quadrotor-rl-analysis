# Trial 25 — xw25: LOW band isolation of the corrected-recipe ingredients

## Why
xw22b bundled 4 changes (γ 0.999, 20 s episodes, true integrator, stiff gains) and
regressed the low band 0.82 → 2.08 median with yaw collapse (trial 22 verdict). The
classical baseline proved two of those ingredients matter (true integrator + settle time:
0.65 median at 20 s under full spec). This trial adds ONLY those two to xw18b's proven
recipe — γ stays 0.99, rate gains stay xwing-default — to isolate their value in RL.

## What (vs xw18b, exactly two changes)
- `--integral-tau 1e6` (true integrator; xw18b: leaky τ=3)
- `--episode-len 20` train/continue/eval (xw18b: 8 s)

## Command (auto chain, queued by scheduler.sh after xw24)
```bash
python train.py --xwing-aero --yaw-bias 0.3 --max-speed 10 --wind-max 15 \
    --yaw-gate --yaw-att-gate --vel-precision 0.7 --cov-width 5 --ent-coef 0.003 \
    --gamma 0.99 --episode-len 20 --integral-tau 1e6 \
    --n-envs 6 --timesteps 8000000 --device cpu --out-dir results_velyaw_xw25 \
&& continue +4M @1e-4 (episode-len 20) && analyze && log_trial
```
No new code (runs on the VecNormSaveCallback-fixed scripts; analyze_velyaw now evaluates
at the trained episode_len by default — exact code in trials 22).

## Pre-registered criteria (20 s eval, 100 eps)
- **SUCCESS**: median ≤ 0.65 (classical ceiling) or mean < 1.89 with yaw < 15° — the
  ingredients transfer to RL; adopt for all bands.
- **NEUTRAL**: ≈ xw18b (0.8–1.0 median) — ingredients neither help nor hurt in RL;
  the classical settle-time gain was protocol-only.
- **FAILURE**: median > 1.5 or yaw > 30° — one of the two ingredients is harmful in RL;
  split further (xw26a: integrator only, xw26b: 20 s only).

## Result
*(auto-appended by log_trial.py when the chain lands)*
