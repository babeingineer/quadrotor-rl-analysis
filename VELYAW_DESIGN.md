# Tailsitter velocity + heading task — design (`task="velyaw"`)

Design only — no training yet. Extends `RateVelAviary` with a **second objective**: on top of
matching a target velocity, the agent must also drive its **heading (yaw) to a commanded angle**.
Everything reuses the proven machinery (CTBR + PID inner loop, disturbance observer, leaky
velocity integrator, sharp `1−tanh` reward peak) and adds a heading channel built the same way.

---

## 1. Task

Two objectives, both held for the whole episode:
1. **Velocity:** current velocity → `target_vel` (random direction on the unit sphere, speed
   `Uniform(0, 25)` m/s).
2. **Heading:** current yaw ψ → `desired_yaw` (`Uniform(−π, π)`).

`target_vel` and `desired_yaw` are sampled **independently** and held **constant per episode**.
`MAX_SPEED = 25` (drives all velocity normalization).

## 2. Initialization (gentle VTOL, replaces the 50%-inverted init)

Each reset:
| quantity | distribution |
|---|---|
| roll  | `Uniform(−40°, +40°)` |
| pitch | `Uniform(−40°, +40°)` |
| yaw   | `Uniform(−180°, +180°)` |
| initial velocity | random unit direction × `Uniform(0, 25)` m/s |
| initial body rates | `Uniform(−1, 1)` rad/s per axis (gentle) |

`quat = p.getQuaternionFromEuler([roll, pitch, yaw])`. Identity (`rpy=0`) is hover (thrust axis
= body-z points up), so ±40° pitch/roll is a moderate tilt, never inverted. This matches your
note that the fully-inverted init was needlessly tough; the ±40° cone keeps us **out of gimbal
lock**, which also makes the yaw definition below well-conditioned.

## 3. What "yaw" means here (the one real subtlety)

A tailsitter has no single obvious "heading" axis: in hover the thrust axis (body-z) points *up*,
in cruise it points *forward*. Definition used:

- **Heading reference = body-x** (the wing-normal / "nose"), projected onto the world horizontal
  plane: `nose = R[:,0]`, **ψ = atan2(nose_y, nose_x)**.
- **Signed yaw error** (wrap-safe): `Δψ = atan2(sin(ψ−ψ_des), cos(ψ−ψ_des)) ∈ [−π, π]`.

In hover body-x is horizontal → ψ is exactly the compass heading, and the yaw-rate channel
(`a_r`, torque about body-z = world-vertical) rotates it cleanly — same as a quadrotor's yaw.

**Degeneracy caveat:** ψ is ill-defined only when body-x is near-vertical (`|nose_z|→1`), i.e.
near ±90° pitch/roll combinations. At ≤25 m/s the craft never needs full 90° wing-borne cruise,
so it stays well-conditioned. If you later push to high-speed cruise, switch the heading
reference to body-z's horizontal azimuth (forward-in-cruise) — noted as an alternative, not needed
for this envelope.

## 4. Observation

Start from the current velocity obs and add **3 heading dims**. Layout (MAX_SPEED = 25):

| block | dims | notes |
|---|---|---|
| velocity error `(target_vel − v)/MAX_SPEED` | 3 | **see frame note below** |
| target velocity `/MAX_SPEED` | 3 | feed-forward |
| rotation matrix `R` | 9 | full attitude (heading is inferable from it) |
| body rates `ω_body/max_rate` | 3 | |
| last action | 4 | |
| motor RPM | 4 | solves motor lag |
| disturbance-observer wind estimate `/hover` | 3 | keep (target-independent) |
| pitot airspeed `/MAX_SPEED` | 1 | |
| leaky **velocity**-error integral `/MAX_SPEED` | 3 | the breakthrough feature — keep |
| **`[sin Δψ, cos Δψ]`** | **2** | **new** — yaw error, wrap-discontinuity-free |
| **leaky yaw-error integral `/π`** | **1** | **new** — nulls steady heading offset |

**Total = 36** (was 33 for the velocity+integrator obs).

- Why sin/cos of Δψ, not raw Δψ: avoids the ±π wrap discontinuity that would put a cliff in the
  observation. Standard for angular targets.
- Why a leaky yaw integral: it's the exact analog of the velocity integrator that was *the* win —
  `dIψ/dt = Δψ − Iψ/τ` (τ≈3 s, clamped to ±π). It nulls a **steady** heading bias (e.g. a
  constant yaw-torque disturbance or motor asymmetry) with zero steady-state error, and forgets
  old transients so it works with a changing setpoint.

**Velocity-error frame — one knob to decide.** Two options:
- **(A) World frame + R** (what the pure-velocity champion used, proven → 4.63 m/s). Simplest,
  minimal change. **Recommend starting here.**
- **(B) Heading frame** — rotate the world velocity error by −ψ about world-z before feeding it.
  Because the agent now *actively holds* a heading, "tilt forward / tilt right" then means the
  same body action regardless of where it's pointing (the yaw-invariant mapping that helped the
  XWing hybrid). Keep R in the obs so nothing is lost. **This is the first thing to A/B if the
  velocity accuracy degrades under the added yaw constraint.**

## 5. Reward

Non-negative while alive (the suicide lesson), each objective with its own **sharp `1−tanh`
peak + wide coverage** (the multi-scale lesson), combined **additively** with a small
**multiplicative joint bonus** so the agent can't nail one and ignore the other.

```
d   = ‖v − target_vel‖                      # m/s
a   = |Δψ|                                   # rad, in [0, π]
s   = MAX_SPEED / 20        (= 1.25)

R_vel = (1 − tanh(d / 2))                    # sharp precision peak (steepest grad at d=0)
      + exp(−0.5 (d / (10·s))²)              # wide coverage, scales to the 25 m/s envelope
R_yaw = (1 − tanh(a / 0.35))                 # sharp peak, ~20° width
      + exp(−0.5 (a / 1.0)²)                 # wide coverage, ~57° sigma → far-field gradient

reward =  w_v · R_vel                        # w_v = 1.0
        + w_y · R_yaw                        # w_y = 1.0
        + λ  · (1 − tanh(d/2)) · (1 − tanh(a/0.35))   # λ = 0.5  JOINT bonus: high only if BOTH nailed
        − (0.02/s) · d                       # gentle far-field pull on velocity (as in the champion)
        + smooth                             # −5e-4(‖ω‖² + ‖Δa‖²), unchanged
if diverged:  reward −= 10
```

- **Balance:** each of `R_vel`, `R_yaw` peaks at ~2 (1 from the tanh + 1 from the exp), so the two
  objectives carry equal weight; the joint term adds up to +0.5 only when both are simultaneously
  tight. Tune `w_y` up if the agent under-serves heading, down if it sacrifices velocity for it.
- **Yaw width (0.35 rad):** matches the achievable heading precision (the "sharpness must match
  reachable precision" lesson — too sharp and it's unreachable/ignored, too flat and it parks in a
  deadband). 0.35 rad ≈ 20° is a sane first guess; tighten toward 0.15–0.2 if it converges cleanly.
- **Smoothness caveat:** the `‖ω‖²` term penalizes body rates *including yaw rate* — keep it tiny
  (5e-4) so it doesn't discourage the yaw corrections the agent must make. Do **not** raise it.

## 6. Domain randomization

Keep all existing DR (per-episode mass, wind, wing area, motor lag). **Optional but recommended:**
add a small **constant per-episode yaw-torque bias** `τ_bias ~ Uniform(−τ_max, τ_max)` applied
about body-z. This is the heading analog of wind — it gives the **yaw integrator something real to
cancel**, so that feature earns its place (exactly as wind justified the wind-estimator/velocity
integrator). Start `τ_max` small (a few % of the max yaw control torque).

## 7. Episode / termination

- Episode length **8 s** (keep — 20 s *regressed* on the velocity task; 8 s lets both leaky
  integrals settle). Consider 10 s only if the yaw integral looks starved.
- Termination: unchanged — **no attitude crash** (a tailsitter legitimately tilts hard); only
  numeric divergence (`|pos|>1e4`) terminates, with −10. Because there's no easy terminal state,
  the mild negativity far from target can't be gamed into "suicide," so the far-field pull is safe.

## 8. Training plan (when you're ready)

- Fresh PPO, `net=[256,256]`, `batch=4096`, `n_steps=2048`, 6 SubprocVecEnv, **CPU** (benchmark
  showed CPU 3.7× faster here). ~8–12 M steps, continued in chunks, frequent checkpoints.
- **Cannot warm-start** from the velocity champion (`results_tsIt`) directly — the obs dim changed
  (33→36). If you want the velocity skill for free, pad the loaded policy's input layer for the 3
  new dims; otherwise just train fresh (simpler, and the velocity part re-learns fast).
- **Optional curriculum** — ramp `w_y` from ~0.2 → 1.0 over the first ~⅓ of training (reuse the
  `DiveCurriculumCallback` pattern) so it locks in velocity first, then heading. Analogous to the
  dive-level ramp. Try flat weights first; add the ramp only if joint learning stalls.
- Watch for the known trap: **stop at saturation** (extra steps past the plateau *regressed*
  4.63→5.35 before). Keep checkpoints and pick the best by eval, not the last.

## 9. Implementation sketch (in `rate_vel_aviary.py`)

- Add `task="velyaw"` alongside `"velocity"`/`"position"`.
- `__init__`: `self.desired_yaw = 0.0`, `self.yaw_integral = 0.0`, `USE_YAW_INTEGRAL` flag,
  `INTEGRAL_TAU` reused, optional `YAW_BIAS_MAX`.
- `_housekeeping`: gentle ±40° init (above); sample `self.desired_yaw`; reset `yaw_integral`;
  sample `τ_bias`.
- `_resample_target`: for `velyaw`, sample `target_vel` (as velocity) **and** `desired_yaw`.
- `step`: after the velocity integral, update the leaky yaw integral from `Δψ`; add `τ_bias` to
  `tau_body` in `_apply_wrench_and_wind` (or in `_control_wrench`).
- `_computeObs`: append `[sin Δψ, cos Δψ]` and (if enabled) `yaw_integral/π`.
- `_computeReward`: the §5 formula for the `velyaw` branch.
- `_computeInfo`: add `yaw_error` (=Δψ) so eval can report heading error in degrees.
- Eval: extend `eval_ts.py` to report both velocity error (by speed band) **and** mean |Δψ| in
  degrees.

## 10. Open decisions for you
1. Velocity-error frame: **world (A, recommended start)** vs heading (B). — the main A/B.
2. Yaw reward width: start **0.35 rad**, tighten later?
3. Add the **yaw-torque disturbance** (§6) to justify the yaw integrator? (recommend yes.)
4. Flat objective weights vs a **`w_y` ramp curriculum**? (recommend flat first.)
