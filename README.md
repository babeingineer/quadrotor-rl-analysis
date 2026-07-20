# RL Quadrotor Velocity Tracking (gym-pybullet-drones + PID rate inner loop)

Reinforcement-learning pipeline that trains a **heavy quadrotor** to **track a random
3-D target velocity under domain randomization (variable mass + wind)**. The RL policy
commands **collective thrust + body rates (CTBR)**; a **PID attitude-rate inner loop**
tracks those rates and computes the control wrench.

- **Task**: match current 3-D velocity to a target. Direction is uniform on the unit
  sphere, speed is `Uniform(0, 20)` m/s (`0` = hover).
- **Airframe (heavy quad)**: mass randomized **Uniform(9, 11) kg per episode**;
  **4 motors, each 0–40 N** (160 N total thrust).
- **Wind**: constant per episode, **random direction, speed `Uniform(0, 20)` m/s**,
  acting through relative-airspeed (quadratic) drag.
- **Sim**: [`gym-pybullet-drones`](https://github.com/utiasDSL/gym-pybullet-drones),
  `Physics.PYB` (real integrator; mass/inertia set per episode, wrench + wind applied
  analytically).
- **Algo**: PPO (Stable-Baselines3) with `VecNormalize`.

## Control architecture

```
 target_vel ─► [ RL policy (PPO) ] ─► CTBR: [thrust, p_sp, q_sp, r_sp]   @ 50 Hz  (ctrl_freq)
                                             │
                                             ▼
                                   [ PID rate inner loop ]  ── ω_body = Rᵀ·ω_world
                                             │                  τ = J·(Kp·e + Ki·∫e)
                                             ▼
                                   [ mixer → 4 motor RPMs ]   @ 500 Hz  (pyb_freq, every substep)
                                             │
                                             ▼
                                   [ PyBullet physics ]
```

The inner loop recomputes the wrench **every physics sub-step** (500 Hz) while the
policy runs at 50 Hz — `RateVelAviary.step()` overrides `BaseAviary.step()` to hold the
policy's CTBR set-point constant across sub-steps.

**Physics handling.** Because the airframe is a large custom quad (arm 0.35 m, 10 kg),
its geometry does not match the CF2X URDF. So instead of relying on per-motor link
positions, the control **wrench is applied analytically**: desired thrust+torque go
through the mixer to per-motor forces, which are **clipped to [0, 40] N (motor
saturation)**; the *achieved* wrench is recomputed from the clipped forces and applied
to the base link via `applyExternalForce`/`applyExternalTorque` (in world frame).
**Mass and inertia are set per episode** with `changeDynamics` (default PyBullet
linear/angular damping is zeroed so wind is the only aero force), and gravity + wind
are integrated by PyBullet. The mixer sign convention matches `BaseAviary._dynamics()`
CF2X and the inner loop is verified empirically in `test_env.py`.

## Files

| File | Purpose |
|------|---------|
| `rate_vel_aviary.py` | The environment: CTBR action, PID rate inner loop, mixer, obs, reward. |
| `train.py` | PPO training with `VecNormalize`, checkpoints, best-model eval callback. |
| `eval.py` | Load a trained policy; report tracking error; optional GUI + plot. |
| `test_env.py` | Sanity checks: inner-loop rate tracking (sign+convergence), hover, Gym API. |

## Environment details

- **Action** `Box(-1, 1, (4,))` = `[a_T, a_p, a_q, a_r]`
  - `a_T`: thrust, centered on the nominal 10 kg hover (`0`→98 N, `+1`→160 N, `-1`→0).
  - `a_p, a_q, a_r`: body-rate set-points, scaled by `±4, ±4, ±2` rad/s.
- **Observation** `(22,)` (all scaled): `[vel_err/vmax (3), target_vel/vmax (3),
  rotation_matrix (9), ω_body/rate_max (3), last_action (4)]` — Markov, gimbal-free.
  Mass and wind are **not** observed → the policy must be robust/adaptive (it corrects
  via the velocity-error feedback, and body-rate commands act as an attitude integrator
  so it can hold a wind-countering tilt with zero steady-state error).
- **Reward**: `exp(-½(d/2)²) + 0.5·exp(-½(d/8)²) − 0.02·d − small(rate, action-jerk)`
  where `d = ‖v − v_target‖`. Two Gaussians give a sharp peak + broad basin; the
  linear term keeps a gradient far from the target. `−10` on crash.
- **Termination**: crash if `|roll|` or `|pitch|` > 85°. Truncation at 8 s.
- Drone/ground collisions are disabled so any target direction (incl. downward) and
  wind drift are valid for the full episode; absolute position is irrelevant.

### Feasibility of 20 m/s
At the nominal 10 kg mass, thrust-to-weight ≈ `160/98 = 1.63`, so max horizontal
accel ≈ `√((160/10)² − 9.8²) ≈ 12.6 m/s²` — the drone reaches 20 m/s in ~1.6 s. Strong
head/tail wind shifts what is achievable per direction; the policy learns to lean into
it. Wind drag is `F = −0.08·|v_rel|·v_rel` (≈32 N at 20 m/s relative airspeed).

## Usage

All commands use the `py311` conda env.

```bash
# 0. sanity checks (fast)
python test_env.py

# 1. train (default: 3M steps, 4 parallel envs)
python train.py --timesteps 3000000 --n-envs 4 --out-dir results
#    quick wiring test:            python train.py --smoke
#    single process (no subproc):  python train.py --no-subproc
#    tensorboard:                  tensorboard --logdir results/tb

# 2. evaluate
python eval.py --out-dir results --episodes 20            # metrics
python eval.py --out-dir results --gui --episodes 3       # watch in PyBullet
python eval.py --out-dir results --plot track.png         # velocity-vs-target plot
```

Outputs land in `results/`: `ppo_ratevel_final.zip`, `best/best_model.zip`,
`vecnormalize.pkl` (needed at eval time), checkpoints, and TensorBoard logs.

## Tuning knobs (`RateVelAviary.__init__`)
- **Airframe / DR**: `mass_range`, `motor_max_thrust`, `arm_length`, `yaw_ratio`,
  `inertia_nominal`.
- **Wind**: `wind_max`, `drag_coeff`.
- **Rate PID**: `kp_rate`, `ki_rate`, `int_limit`, `max_rate_rp`, `max_rate_yaw`.
  Re-run `test_env.py` after changing these to re-verify inner-loop tracking.
- **Task**: `max_speed`, `episode_len_sec`.
- **PPO** (`train.py`): `net_arch`, `learning_rate`, `n_steps`, `batch_size`.

## Setup (already done in this env)
```bash
pip install pybullet transforms3d
pip install -e gym-pybullet-drones --no-deps   # protects existing sb3/torch/gymnasium/numpy
```
`--no-deps` is used because gym-pybullet-drones pins older `gymnasium`/`numpy`; the
installed stack (gymnasium 1.2.3, numpy 2.2.5, SB3 2.8.0, torch 2.6.0) is verified
to run the sim.
