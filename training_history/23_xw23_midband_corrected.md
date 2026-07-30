# Trial 23 — LOOP: mid band with the CORRECTED recipe (first fair RL test at speed)

| | |
|---|---|
| run dirs | `results_velyaw_xw23` → `xw23b` (converge) |
| date | 2026-07-30 |
| context | ALL prior mid/high RL runs used the leaky integrator + short episodes — the two artifacts PROVEN binding in the low band. Never tested corrected at speed. Classical ceiling probe: mid-band **median 0.20 m/s** (60% < 1) — task doable at speed; residual = robustness across DR draws = RL's home turf. |
| changes | mid band (10–18) + **integral_tau 1e6 (true integrator)** + **20 s episodes** + γ 0.999 + stiff gains + full stack |
| target | convert the classical's "stable majority" into (nearly) all episodes: mean ≤ 2, median ≤ 0.5 |

## Command (auto chain, script file run_xw23.sh)
```bash
python train.py --xwing-aero --yaw-bias 0.3 --max-speed 18 --speed-min 10 --wind-max 15 \
    --yaw-gate --yaw-att-gate --vel-precision 0.7 --cov-width 5 --ent-coef 0.003 \
    --gamma 0.999 --episode-len 20 --integral-tau 1e6 --kp-rate 40,40,25 --ki-rate 10,10,5 \
    --n-envs 6 --timesteps 8000000 --device cpu --out-dir results_velyaw_xw23 \
&& continue +4M @1e-4 (ep 20) && analyze && log_trial
```

## CRASH + QUEUED RELAUNCH (2026-07-30 22:2x)
First attempt OOM-died at 2,015,232 steps (`numpy ArrayMemoryError` — same Windows commit
exhaustion that killed xw22; "paging file too small" DLL errors hit lstm3 at the same time).
Launched BEFORE the VecNormSaveCallback fix -> no vecnormalize.pkl -> not resumable.
Relaunch queued via `scheduler.sh` (RAM-staggered: max 2 chains at once): waits for the
xw22b chain to finish, then reruns this chain fresh with the resumable train.py, then
auto-launches xw24 (high band). Eval reward at death was still climbing (-594 -> -498, new
bests) — no verdict.

## RECIPE REVISED before relaunch (2026-07-31 00:5x) — γ 0.999 → 0.997
xw22b's verdict landed first: the 4-variable recipe at γ 0.999 REGRESSED the low band
(0.82 → 2.08 median) with the known γ≈1 yaw collapse (53°). The first xw23 attempt (same
γ 0.999) was killed at ~10 min rather than spend half a day on a demonstrated-poisoned
config. Relaunched with **--gamma 0.997** — the value that produced the best-ever velocity
at speed (xw17 high band 8.58) — keeping true integrator + 20 s episodes + stiff gains.
```bash
# run_xw23.sh (revised line)
--gamma 0.997 --episode-len 20 --integral-tau 1e6 --kp-rate 40,40,25 --ki-rate 10,10,5
```
