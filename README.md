# RL Drone Control — heavy quadrotor → tailsitter VTOL (gym-pybullet-drones)

A reinforcement-learning control pipeline built on
[gym-pybullet-drones](https://github.com/utiasDSL/gym-pybullet-drones) with a **PID
attitude-rate inner loop**. The RL policy commands **collective thrust + body rates
(CTBR)**; the inner loop tracks those rates and applies the control wrench. The project
grew through three phases:

1. **Heavy quadrotor** (≈10 kg) — track a random 3-D velocity, and separately reach/hold a
   3-D position (go-to / hover), under domain randomization (mass, wind, motor lag).
2. **Tailsitter VTOL** — converted the airframe to a light (2–5 kg) tailsitter with **fixed
   wings** (flat-plate lift/drag). Task: track a **random 3-D velocity, 0–80 m/s, in any
   direction** (it must pitch ~90° to fly on the wings).
3. **Investigations** — reward design, a **velocity-error integrator** in the observation
   (the single biggest win), and a memory study (plain MLP vs frame-stacking vs LSTM).

## Headline results
- **Quad velocity tracking:** 0.82 m/s mean error, 0% crashes, robust to 20 m/s wind.
- **Quad position / hover:** 0.06 m hover, 0.33 m step overshoot (with enough training).
- **Tailsitter velocity (0–80 m/s, omnidirectional, full domain randomization):** **4.63 m/s**
  mean error, **0% crashes**, learned hover→cruise transition, climb, and dives. The two levers
  that did it: a **leaky velocity-error integrator** in the observation (8.1 → 4.8 m/s) and a
  **sharp reward peak** (→ 4.63). More network width, more raw training, frame-stacking, and
  curriculum did **not** help.
- **Memory study:** **LSTM > plain MLP > frame-stacking** (frame-stack was *worst* — its ~80 ms
  window of near-duplicate frames added little and hurt), and even the LSTM did better *with*
  the hand-designed wind-estimator + integrator features than without.

## Documentation — start here
| Doc | What's in it |
|---|---|
| **[SUMMARY.md](SUMMARY.md)** | Final-state summary: the quad velocity + position tasks and the tailsitter extension, with figures. |
| **[TAILSITTER.md](TAILSITTER.md)** | The **main detailed log** of the tailsitter investigation — every training run (config + what changed + result), every reward, every diagnostic/ablation, the memory study, and the lessons drawn. |
| **[TRAINING_HISTORY.md](TRAINING_HISTORY.md)** | Chronological log of the quadrotor runs (velocity + position). |
| **[LESSONS.md](LESSONS.md)** | Deep, generalizable takeaways (reward-design traps, sense-vs-infer observations, when memory helps, training-dynamics pitfalls, physical vs learnable limits). |

*(Run names in the docs are descriptive — e.g. `champion`, `hard-corner`, `deeper-net`,
`integrator-8M`. The saved models live in the matching `results_*` directories.)*

## Control architecture

```
 target ─► [ RL policy (PPO) ] ─► CTBR: [thrust, p_sp, q_sp, r_sp]   @ 50 Hz  (ctrl_freq)
                                         │
                                         ▼
                               [ PID rate inner loop ]  ── ω_body = Rᵀ·ω_world
                                         │                  τ = J·(Kp·e + Ki·∫e)
                                         ▼
                               [ mixer → per-motor forces ]  @ 500 Hz  (pyb_freq, every substep)
                                         │
                                         ▼
                               [ PyBullet physics + wind + wing aero ]
```

The inner loop recomputes the wrench **every physics sub-step** (500 Hz) while the policy
runs at 50 Hz — `RateVelAviary.step()` holds the policy's CTBR set-point constant across
sub-steps. Because the airframe is custom (not the CF2X URDF geometry), the control
**wrench is applied analytically**: desired thrust+torque go through the mixer to per-motor
forces, which are **clipped to motor saturation**; the *achieved* wrench is recomputed from
the clipped forces and applied to the base link. **Mass, inertia, wing area, and motor lag**
are set per episode; gravity, wind drag, and (tailsitter) flat-plate wing lift/drag are
integrated by PyBullet. The inner loop is verified empirically in `test_env.py`.

## Environment & observation (in brief)
- **Action** `Box(-1, 1, (4,))` = CTBR `[thrust, roll_rate, pitch_rate, yaw_rate]`.
- **Observation (memoryless MLP):** velocity error, target, rotation matrix (gimbal-free),
  body rates, last action, **motor RPM** (exposes actuator state → beats frame-stacking), a
  **disturbance-observer wind estimate**, and (tailsitter) a pitot airspeed + a **leaky
  velocity-error integral**. Mass/wind are *not* observed directly — the policy is robust via
  velocity-error feedback and infers disturbance from the observer term.
- **Reward:** velocity task — sharp (Gaussian/tanh) peaks on the velocity error + small
  smoothness penalties, `−10` on crash; position task — a non-negative baseline + exponential
  terminal bonus. See the docs for the exact forms and *why* each shape was chosen.
- **Termination:** crash on excessive attitude; truncation at the episode length (8 s).
- **Domain randomization:** per-episode mass, wind (0–20 m/s any direction), motor-lag time
  constant, wing area; plus an optional tough initial state (inverted attitude, high speed,
  tumbling) used to teach recovery/dive.

## Key files
| File | Purpose |
|---|---|
| `rate_vel_aviary.py` | The environment: CTBR action, PID rate inner loop, mixer, motor lag, wind, disturbance observer, wing aero, both tasks, all observation/reward options. |
| `train.py` | PPO training (VecNormalize, frame-stack via `--n-stack`, `--use-integral` / `--no-wind-est`, `--net`, checkpoints, eval callback). |
| `train_lstm.py` | Recurrent-PPO (LSTM) training for the memory study. |
| `continue_train.py` | Resume/continue training from a saved run (more steps, reward swap, DR ramp, dive curriculum). |
| `eval_ts.py` / `eval_mem.py` | Tailsitter evaluation (velocity error by speed band; memory-policy eval through the real vec stack). |
| `eval.py` | Quad evaluation: tracking error, optional GUI + plot. |
| `test_env.py` | Env sanity checks (inner-loop rate tracking, hover, wind, observer, saturation). |
| `gen_summary_figs.py` / `gen_all_inference_figs.py` | Regenerate the figures used in the docs. |

## Usage
All commands use the `py311` conda env.
```bash
python test_env.py                                              # sanity checks

# quadrotor velocity task
python train.py --timesteps 3000000 --n-envs 6 --out-dir results
python eval.py --out-dir results --episodes 20

# tailsitter velocity task (0–80 m/s omnidirectional): the integrator is the key lever
python train.py --timesteps 8000000 --n-envs 6 --use-integral --out-dir results_integrator
python continue_train.py --src results_integrator --out results_integrator2 --extra 4000000
python eval_ts.py                                               # velocity error by speed band

# memory study
python train.py --n-stack 4 --use-integral --out-dir results_framestack   # frame-stacking
python train_lstm.py --use-integral --out-dir results_lstm                # LSTM

tensorboard --logdir results_integrator/tb
```

## Setup (already done in this env)
```bash
pip install pybullet transforms3d sb3-contrib
pip install -e gym-pybullet-drones --no-deps   # protects the installed sb3/torch/gymnasium/numpy
```
`--no-deps` avoids gym-pybullet-drones' older gymnasium/numpy pins; the installed stack
(gymnasium 1.2.3, numpy 2.2.5, SB3 2.8.0, sb3-contrib 2.8.0, torch 2.6.0) runs the sim.
