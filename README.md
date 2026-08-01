# RL Tailsitter Velocity Control (velyaw)

Full-RL velocity + heading control for a tailsitter VTOL (14 kg, 4×110 N motors, ±20°
elevons, ported XWing aerodynamic model) in PyBullet, built on
[gym-pybullet-drones](https://github.com/utiasDSL/gym-pybullet-drones).

**Task:** track a random 3-D target velocity (goal envelope 0–45 m/s) AND a commanded
heading, under per-episode wind (0–15 m/s) and ±20% domain randomization of aero
coefficients, mass, motor lag, and servo gain. The policy (PPO, MLP 256×256) commands
collective thrust + elevons + an attitude/rate setpoint; a PID inner loop runs at 500 Hz.

## Current results (steady-state velocity error, full randomization)

| band | median | %<1 m/s | notes |
|---|---|---|---|
| hover 0–1 | 0.61 | 86% | solved |
| low 1–10 | 0.88 | 57% | sub-1 typical; residual = strong-wind tail |
| mid 10–18 | **1.09** [CI 0.99–1.20] | 45% | improving; sub-1 under calm wind |
| high 18–25 | 5.88 | — | best recipe transferring next |

## Key findings (details in [training_history/](training_history/INDEX.md))

- **Trim feasibility proven everywhere**: exact force-balance trims exist for 100% of
  target/wind/DR draws in the envelope — every residual is controller quality, not physics.
- **Goal-state initialization (trim-init)**: starting a fraction of training episodes at
  the target velocity in near-trim attitude was the single biggest gain at speed.
- **Attitude-setpoint action space**: the wing-borne trim is dynamically unstable; letting
  an inner attitude-P loop stabilize it structurally (policy commands setpoints) beats
  raw body-rate commands by a wide margin.
- **Negative results that matter**: LSTM ≪ MLP; privileged critic, reward sharpening,
  bigger nets, and removing domain randomization all failed controlled tests.

## Quickstart

```bash
pip install -r requirements.txt
pip install gym-pybullet-drones

python build_trim_table.py        # one-time: trim table for trim-init / analysis (~1 min)

# train a mid-band specialist (attitude interface + trim-init)
python train.py --xwing-aero --yaw-bias 0.3 --max-speed 18 --speed-min 10 --wind-max 15 \
    --yaw-gate --yaw-att-gate --vel-precision 0.7 --cov-width 5 --ent-coef 0.003 \
    --trim-init 0.2 --att-cmd --timesteps 8000000 --out-dir results_velyaw_run1

python continue_train.py --src results_velyaw_run1 --out results_velyaw_run1b \
    --extra 4000000 --lr 1e-4                       # convergence stage (essential)

python analyze_velyaw.py --dir results_velyaw_run1b # physical eval + recovery + traces
```

## Repository map

| path | contents |
|---|---|
| `rate_vel_aviary.py` | the environment (obs/action/reward, DR, inner PID, trim-init) |
| `aero_xwing.py` | ported XWing aerodynamic model (byte-faithful) |
| `train.py` / `continue_train.py` / `train_lstm.py` | training entry points |
| `eval_velyaw.py` / `analyze_velyaw.py` / `eval_inflight.py` | evaluation (distribution metrics, dive-recovery, hold-from-trim diagnostic) |
| `classical_baseline.py` | hand-tuned cascade used as a diagnostic ceiling probe |
| `priv_policy.py` | asymmetric actor-critic policy (critic-only privileged obs) |
| `build_trim_table.py` | offline trim solver (speed × path-angle grid) |
| `training_history/` | one MD per training run: change, config, results, verdict — plus [INDEX](training_history/INDEX.md), [JOURNEY](training_history/JOURNEY.md), [ULTIMATE_PLAN](training_history/ULTIMATE_PLAN.md) |
| `docs/` | prior-project logs — heavy quadrotor and the 0–80 m/s tailsitter study ([SUMMARY](docs/SUMMARY.md), [TAILSITTER](docs/TAILSITTER.md), [LESSONS](docs/LESSONS.md)) — and figures |
| `legacy/` | superseded entry points kept for reference |
