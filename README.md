# RL Tailsitter Velocity Control (velyaw)

Full-RL velocity + heading control for a tailsitter VTOL (14 kg, 4×110 N motors, ±20°
elevons, ported XWing aerodynamic model) in PyBullet, built on
[gym-pybullet-drones](https://github.com/utiasDSL/gym-pybullet-drones).

**Task:** track a random 3-D target velocity (goal envelope 0–45 m/s) AND a commanded
heading, under per-episode wind (0–15 m/s) and ±20% domain randomization of aero
coefficients, mass, motor lag, and servo gain. The policy (PPO, MLP 256×256) commands
collective thrust + elevons + an attitude/rate setpoint; a PID inner loop runs at 500 Hz.

## Current results

Composite of four band specialists routed by commanded speed, with a full-envelope generalist
armed underneath as an upset-recovery mode. 400 nominal + 240 failure-state episodes under full
randomization (`python eval_composite.py --episodes 400 --upsets 60 --recovery`).

| band | median vel err | p90 | %<1 m/s | recovery from upset | notes |
|---|---|---|---|---|---|
| hover 0–1 | 0.27 | 2.18 | 80% | — | solved |
| low 1–10 | 0.44 | 3.08 | 75% | 60% | solved |
| mid 10–18 | 0.77 | 7.12 | 64% | 57% | solved |
| high 18–25 | 1.77 | 14.45 | 27% | 35% | beats the classical cascade (3.90), misses the goal |
| vhigh 25–34 | 5.73 | 18.79 | 3% | 32% | coverage only; switch unarmed (see limits) |
| **pooled** | **1.22** [CI 1.04–1.60] | **13.98** | **44%** | **46%** [CI 40–53] | vs 22% [17–28] unarmed |

Precision degrades with wind as expected: median 0.90 (0–5 m/s), 1.23 (5–10), 2.51 (10–15).

**What the recovery mode costs.** Arming is a paired comparison against the same seeds (the
harness is deterministic: 379 of 400 episodes are byte-identical between arms, max difference
0.00). It engages on 4% of nominal flights; on those 16 episodes mean error goes 21.18 → 15.36,
helping 9 and hurting 7, with improvements outweighing regressions 7.4:1 by magnitude (worst
single regression +9.71 m/s). Pooled median is unchanged and pooled p90 improves 14.62 → 13.98.
So it is **net beneficial with real per-episode variance** — not free, and not costly.

### Honest limits

- **The goal is met on 0–18 m/s, not above it.** 18–25 lands at 1.77 median, and 25–34 at 5.73.
  **34–50 m/s is not covered by any trained policy** — trims exist there (verified within
  actuator limits), but no policy flies it. The goal envelope moved 0–25 → 0–45 → 0–50 m/s during
  the campaign; the numbers above are the honest state against the widest of those.
- **One wide-range policy was never achieved.** The deliverable is four band specialists plus a
  routing rule. Trial 70 identifies a concrete, quantified reason (reward scale) and implements a
  fix, but it was **never trained**, so single-policy feasibility remains open rather than
  refuted.
- **Tail statistics are seed-sensitive at n≈100/band.** The same armed/disarmed comparison
  showed p90 rising on the seed set the detector was calibrated on and falling on a fresh one.
  Detector thresholds are selected on seeds 5000+/1000+ (`calib_upset.py`) and the composite
  scores from 20000+ to keep selection out of sample; per-band numbers should not be read to
  better than ~10%.
- **Precision and coverage trade off**, measured: stretching a specialist to 40 m/s degraded
  its own 25–34 band from 3.77 to 5.30. This is why the system is banded rather than single.
- **The recovery switch is arming-gated.** The generalist trained to 25 m/s, so arming it above
  that made recovery *worse* (28% → 5% on the 25–34 band). It is armed only where in-envelope.
- Recovery is measured from synthetic failure-state starts in simulation; no hardware, and no
  sim-to-real transfer is claimed.

## Key findings (details in [training_history/](training_history/INDEX.md))

- **Trim feasibility proven everywhere, to 60 m/s**: exact force-balance trims exist for 100% of
  target/wind/DR draws — every residual is controller quality, not physics. The solver clips
  elevator to ±20° and thrust to 440 N *before* scoring the residual
  ([build_trim_table.py:31](build_trim_table.py#L31)), so its ~1e-10 residuals are actuator-feasible;
  stored deflections beyond 20° are unclipped optimizer coordinates in a flat direction, not
  infeasible trims. (An earlier note in this project claimed 60 m/s "needs −21° elevator, so it
  isn't flyable" — that was wrong for exactly this reason.) Level flight at 50 m/s needs 134 N of
  the 440 N available.
- **The wide-range failure is a reward-scaling artifact, not capacity or interference** (trial
  70, analysis only): all velocity reward terms have absolute widths, so the shaped gradient at
  an episode's start falls from 1.3e-1 at 5 m/s to **3.9e-22 at 50 m/s**, and the one surviving
  term is scaled `0.4/MAX_SPEED` — asking for a wider envelope weakens it. This retro-explains
  why trim-init helped most at speed, why fresh fast-band runs failed, and why more fast-band
  training always hurt. A scale-invariant approach reward is implemented (`--rel-approach`) and
  **untrained**.
- **Goal-state initialization (trim-init)**: starting a fraction of training episodes at
  the target velocity in near-trim attitude was the single biggest gain at speed.
- **Attitude-setpoint action space**: the wing-borne trim is dynamically unstable; letting
  an inner attitude-P loop stabilize it structurally (policy commands setpoints) beats
  raw body-rate commands by a wide margin.
- **Robustness is a state-coverage property, not a curriculum knob.** Band specialists recover
  from upsets far worse than a full-envelope generalist, and the generalist never trained on
  failure states at all (`tough_init=0`) — breadth of experience is the whole mechanism.
  Reintroducing failure-state training moved recovery 12% → 22% but walked precision 0.82 →
  0.97, onto the goal line. Routing upsets to the generalist instead nearly doubles pooled
  recovery (22% → 46%) and is **net positive on precision too** (paired: 21.18 → 15.36 mean on
  the 4% of flights it engages, improvements outweighing regressions 7.4:1).
- **Detectors must be calibrated against data, per band.** An upset detector hand-tuned on one
  band fired in 47% of *normal* flights across the roster: a tailsitter's cruise is
  near-horizontal (nominal tilt p95 reaches 110°), so an absolute tilt limit flags ordinary fast
  flight, and these policies routinely exceed a 2.5 rad/s body-rate limit. Comparing tilt to
  the *trim attitude the command implies*, plus dwell, cut spurious firing 16× to 3%.
- **Negative results that matter**: LSTM ≪ MLP; privileged critic, reward sharpening,
  bigger nets, and removing domain randomization all failed controlled tests. Also refuted with
  measurements: 100 Hz control (retested fairly after a hyperparameter confound), PID-teacher
  distillation, airflow observability, integral memory (×3), and band splitting.

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

# UNTRAINED (trial 70): single policy over the full range needs a scale-invariant approach
# reward, or the objective is numerically dead at speed. Legacy is unchanged at rel-approach 0.
# python train.py --xwing-aero --speed-min 0 --max-speed 50 --rel-approach 1.0 ...

python analyze_velyaw.py --dir results_velyaw_run1b # physical eval + recovery + traces

# the full system: route by commanded speed, generalist armed for upset recovery
python eval_composite.py --episodes 400 --upsets 60 --recovery
```

## Repository map

| path | contents |
|---|---|
| `rate_vel_aviary.py` | the environment (obs/action/reward, DR, inner PID, trim-init) |
| `aero_xwing.py` | ported XWing aerodynamic model (byte-faithful) |
| `train.py` / `continue_train.py` / `train_lstm.py` | training entry points |
| `eval_velyaw.py` / `analyze_velyaw.py` / `eval_inflight.py` | evaluation (distribution metrics, dive-recovery, hold-from-trim diagnostic) |
| `eval_composite.py` | the deliverable: band routing + optional recovery mode, precision AND recovery columns |
| `recovery_switch.py` / `eval_recovery_switch.py` | supervisory upset-recovery switch (routing rule over two trained nets) |
| `calib_upset.py` / `diag_upset_terms.py` | detector threshold calibration and per-term false-fire attribution |
| `classical_baseline.py` | hand-tuned cascade used as a diagnostic ceiling probe |
| `priv_policy.py` | asymmetric actor-critic policy (critic-only privileged obs) |
| `build_trim_table.py` | offline trim solver (speed × path-angle grid) |
| `training_history/` | one MD per training run: change, config, results, verdict — plus [INDEX](training_history/INDEX.md), [JOURNEY](training_history/JOURNEY.md), [ELIMINATED](training_history/ELIMINATED.md) (all refuted mechanisms, with numbers), [ULTIMATE_PLAN](training_history/ULTIMATE_PLAN.md) |
| `docs/` | prior-project logs — heavy quadrotor and the 0–80 m/s tailsitter study ([SUMMARY](docs/SUMMARY.md), [TAILSITTER](docs/TAILSITTER.md), [LESSONS](docs/LESSONS.md)) — and figures |
| `legacy/` | superseded entry points kept for reference |
