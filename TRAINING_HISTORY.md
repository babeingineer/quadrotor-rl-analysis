# Training History — full detail for every run

Chronological log of all training runs (including failures). For **each** run:
environment, **exact observation vector**, **exact reward function**, **exact
hyperparameters**, **exact results**, and *why we changed it next*.

Jump to the master table → [below](#master-table). Shared definitions (env, observation
layouts, config blocks) are defined once here, then referenced per run.

---

## Shared definitions

### Env base (heavy quad; all runs from T2 on)
```
mass            ~ Uniform(9, 11) kg  (per episode; inertia scales with mass)
motors          4 × [0, 40] N  -> 160 N max total thrust
arm 0.35 m,  yaw torque ratio KM/KF = 0.02,  inertia diag(0.20,0.20,0.35)@10kg
wind            constant/episode, random direction, |w| ~ Uniform(0,20) m/s
                drag  F_wind = -0.08 * |v-w| * (v-w)
control         policy @ 50 Hz,  PID rate inner loop @ 500 Hz (10 substeps/step)
episode         8 s = 400 policy steps; crash (terminate) if |roll| or |pitch| > 85 deg
constants       MAX_SPEED=20, MAX_RATE=(4,4,2) rad/s, NOMINAL_HOVER=98 N, POS_RANGE=30 m
```
**Motor lag** (added at T4): each motor's thrust is a first-order lag toward command,
time-constant `τ ~ Uniform(0.10, 0.25) s` per episode.
**PID inner-loop gains:** T2–T3 `kp=(12,12,8), ki=(2,2,1)`; **T4 onward** lowered to
`kp=(6,6,4), ki=(0.5,0.5,0.3)` (lag in the loop needs lower gain).

### Observation layouts (all components normalized as shown)
- **OBS-V22** (velocity task, T1–T3):
  `[ (v_target−v)/20 (3), v_target/20 (3), R (9), ω_body/MAX_RATE[0] (3), last_action (4) ]`
- **OBS-V88** (T4–T5): OBS-V22 **frame-stacked ×4** = 88.
- **OBS-V29** (velocity task, T6–T8): OBS-V22 **+** `motor_rpm (4)` **+** `wind_est/98 (3)`
  where `motor_rpm = √(motor_force/40)` (ESC telemetry) and `wind_est` = disturbance
  observer `F ≈ m·a − R·[0,0,T] + [0,0,mg]` (EMA-filtered).
- **OBS-P29** (position task, T10–T16):
  `[ clip(p_target−p, |·|≤30)/30 (3), v/20 (3), R (9), ω_body/MAX_RATE[0] (3), last_action (4), motor_rpm (4), wind_est/98 (3) ]`

### Config blocks
- **PPO-default:** `n_steps=2048, batch=4096, n_epochs=10, γ=0.99, gae_λ=0.95,
  clip=0.2, ent=0.0, lr=3e-4, net=[128,128]`, 6 envs, VecNormalize(obs+reward).
- **SAC-default (untuned):** `lr=3e-4, batch=256, net=[128,128], τ=0.005, γ=0.99,
  train_freq=(1,step), gradient_steps=n_envs, buffer=400k, learn_starts=10k,
  ent_coef=auto`, 4 envs, VecNormalize(obs only).
- **SAC-tuned:** `lr=1e-4, batch=512, net=[256,256], τ=0.005, gradient_steps=2,
  buffer=600k, learn_starts=15k, gSDE on, ent_coef=auto`, 4 envs.
- **smooth** (in every reward): `−5e-4·‖ω_body‖² − 5e-4·‖a − a_prev‖²`.

---

## Master table

| # | Run | Algo | Obs | Steps | Key result | Verdict |
|---|---|---|---|---|---|---|
| T1 | light-drone velocity | PPO | V22 | ~1.8M | ~350–430 return | ✅ spec changed |
| T2 | heavy velocity, no lag | PPO | V22 | 3M | 2.86 m/s, 50% crash>15 | ⚠️ |
| T3 | heavy velocity, no lag | SAC | V22 | 500k | 3.48 m/s, drifts down | ❌ |
| T4 | +lag, frame-stack | PPO | V88 | 3M | 1.74 m/s, 12.5% crash>15 | ✅ |
| T5 | +lag, frame-stack | SAC | V88 | 500k | 4.33 m/s | ❌ |
| **T6** | **RPM+observer** | **PPO** | **V29** | 3M | **0.82 m/s, 0% crash** | ⭐ vel final |
| T7 | RPM+observer | SAC | V29 | 500k | 4.09 m/s, 50% crash>15 | ❌ |
| T8 | RPM+observer, tuned | SAC | V29 | 800k | 1.48 m/s, 2% crash | ✅ 2nd |
| T9 | position, range=5 | PPO | P29 | stopped | — | ❌ config |
| T10 | position, negative reward | PPO | P29 | stopped 1.9M | ep_len 25/400, ret −25 | ❌ suicide |
| T11 | position, Gaussian σ1.5 | PPO | P29 | 3M | hover 0.52 m | ⚠️ deadband |
| T12 | position, exp σ0.3 | PPO | P29 | 3M | hover 2.31 m | ❌ too sharp |
| T13 | position, exp σ1.0 | PPO | P29 | 3M | hover 0.61 m | ⚠️ |
| T14 | position, continue | PPO | P29 | 6M | hover 0.19 m | ✅ |
| T15 | position, +stop-dist | PPO | P29 | 9M | hover 0.12 m, overshoot 2.6 m | ⚠️ |
| **T16** | position, pure reward | PPO | P29 | 12M | **hover 0.06 m, overshoot 0.33 m** | ⭐ pos final |

---

# Era 1 — Light drone, velocity (T1)

### T1 · PPO · CF2X Crazyflie (27 g) · velocity
- **Env:** stock-ish CF2X, `Physics.PYB` (drag-free), **no** wind/mass-DR/motor-lag.
  `MAX_RATE=(6,6,3)`, thrust-to-weight 2.25.
- **Observation — OBS-V22** (22): `[(v_target−v)/20, v_target/20, R(9), ω_body/6, last_action(4)]`.
- **Reward** (velocity reward, used unchanged T1–T8):
  ```
  d = ‖v − v_target‖
  r = exp(−0.5·(d/2)²) + 0.5·exp(−0.5·(d/8)²) − 0.02·d + smooth ;   crash: −10
  ```
- **Algo:** PPO-default (4 envs).
- **Result:** reached ~**350–430 eval return** by ~1.8M steps; velocity tracking clearly
  working. No aggregate error metric recorded (superseded before final eval).
- **Why next:** user redefined the airframe → **heavy quad (9–11 kg), 4×40 N motors,
  wind 0–20 m/s**. Rebuilt the env (custom mass/inertia/thrust, analytic wrench, wind drag,
  mass DR).

---

# Era 2 — Heavy drone, velocity, NO motor lag (T2, T3)

Env = Env-base **without** motor lag. `MAX_RATE=(4,4,2)`, PID `kp=(12,12,8)`.
Both use **OBS-V22** and the **velocity reward** (see T1).

### T2 · PPO · `results` · 3M
- **Algo:** PPO-default (6 envs). ~32 min.
- **Result (50 identical scenarios):**

  | mean err | median | err (tgt≤15) | non-crash err | crash all | crash >15 |
  |---|---|---|---|---|---|
  | **2.86 m/s** | 1.09 | 1.36 | 1.35 | 12% | **50%** |

  Diagnostic (100 scenarios): ~29/40 track well (≤15 m/s → 0% crash), the failures are
  **16–20 m/s targets crashing** (aggressive tilt + thrust-envelope corner).
- **Bug fixed here:** `self.DRAG_COEFF` was overwritten by the URDF parser (wind ≈ 0) →
  renamed `WIND_DRAG`.
- **Why next:** compare against SAC.

### T3 · SAC · `results_sac` · 500k
- **Algo:** SAC-default (4 envs). ~62 min.
- **Result (same 50 scenarios):** mean **3.48 m/s**, crash 12%, crash>15 50%.
  Learning curve **peaked ~399 @250k then drifted down** — SAC instability under heavy DR.
- **Verdict:** PPO > SAC; both crash at high speed.
- **Why next:** user added **motor lag** — the ESC takes **100–250 ms** to reach a
  commanded RPM. Large vs the 20 ms policy step → partial observability + slower inner loop.

---

# Era 3 — Motor lag + frame-stacking (T4, T5)

Env-base **with** motor lag (`τ~U(0.10,0.25)s`); PID lowered to `kp=(6,6,4), ki=(0.5,0.5,0.3)`
(re-verified rate-tracking stable at worst-case τ). To let a memoryless MLP cope with the
hidden motor state, the obs is **frame-stacked ×4** → **OBS-V88**. Velocity reward unchanged.

### T4 · PPO · `results_fs` · 3M
- **Obs:** OBS-V88. **Algo:** PPO-default + `VecFrameStack(4)`.
- **Result (50 scenarios):**

  | mean err | median | err (≤15) | non-crash | crash all | crash >15 |
  |---|---|---|---|---|---|
  | **1.74 m/s** | 0.97 | 1.36 | 1.09 | 6% | **12.5%** |

  Better than T2 *despite the harder (lagged) env* — mostly the gentler retuned PID + history.
- **Why next:** compare SAC.

### T5 · SAC · `results_sac_fs` · 500k
- **Obs:** OBS-V88. **Algo:** SAC-default + `VecFrameStack(4)`, buffer 400k.
- **Bug fixed here:** SAC crashed on start — with `VecFrameStack(VecNormalize(...))`, the
  off-policy buffer (sized for stacked obs, 88) received the **un-stacked** original obs (22)
  from `get_original_obs()`. Fix: put **VecNormalize on the outside** of VecFrameStack.
- **Result (50 scenarios):** mean **4.33 m/s**, median 1.75, crash 24%, crash>15 37.5%. Still
  unstable (peak-then-drift).
- **Verdict:** PPO+FS strong; SAC still unstable.
- **Why next:** user noted **RPM is readable from the ESC**, proposed feeding it in + an
  integral for wind. We converged on **RPM + a disturbance-observer wind estimate**
  (directly *sensing* the hidden states, and target-independent so it transfers to changing
  targets) with `n_stack=1`.

---

# Era 4 — Motor RPM + disturbance observer (T6, T7)

Env unchanged (lag env). **OBS-V29** = OBS-V22 + `motor_rpm(4)` + `wind_est/98(3)`.
Observer: `F_wind ≈ m·a − R·[0,0,T] + [0,0,mg]` with nominal mass, EMA-filtered (verified to
recover the true wind force to ~0 N). Velocity reward unchanged. `n_stack=1`.

### T6 · PPO · `results_obs` · 3M — VELOCITY FINAL ⭐
- **Obs:** OBS-V29. **Algo:** PPO-default.
- **Result (50 scenarios):** mean **0.82 m/s, median 0.72, 0% crash (0% >15).**
  100-scenario breakdown:

  | slice | mean err | crash |
  |---|---|---|
  | overall | 1.28 | 4% |
  | calm (≤7 m/s wind) | 0.92 | 3% |
  | moderate (7–14) | 1.47 | 5% |
  | **strong wind (>14)** | **1.48** | **4%** |
  | target ≤15 m/s | **0.61** | **0%** |
  | target >15 m/s | 3.39 | 17% |

  **Wind is solved** (strong wind ≈ calm). Direct sensing beat frame-stacking (0.82 vs 1.74).
  Residual = the >15 m/s thrust-envelope corner (physical).
- **Why next:** compare SAC on same obs.

### T7 · SAC · `results_sac_obs` · 500k
- **Obs:** OBS-V29. **Algo:** SAC-default.
- **Result:** mean **4.09 m/s**, median 2.26, crash 18%, crash>15 50%. Better observation did
  **not** rescue SAC (its bottleneck is optimization stability, not sensing).
- **Why next:** user asked to **tune SAC**.

---

# Era 5 — SAC tuning (T8)

### T8 · SAC-tuned · `results_sac_tuned` · 800k
- **Obs:** OBS-V29 (same as T6/T7). **Reward:** velocity reward (same).
- **Algo — SAC-tuned:** deltas from SAC-default → `lr 3e-4→1e-4`, `batch 256→512`,
  `net [128,128]→[256,256]`, `gradient_steps 4→2`, `buffer 400k→600k`, `learn_starts 10k→15k`,
  **gSDE on**. ~72 min.
- **Result (50 scenarios, vs T6 PPO):**

  | | PPO (T6) | SAC-tuned (T8) |
  |---|---|---|
  | mean err | **0.82** | 1.48 |
  | crash all | **0%** | 2% |
  | crash >15 | 0% | 0% |

  A **2.7× improvement** over untuned SAC (T7: 4.09→1.48). Curve still peaks (~468 @250k) then
  bounces down — improved but not cured. Most impactful knobs: **lr↓ and gSDE**.
- **Verdict:** PPO still wins; SAC's instability under heavy DR is structural. **PPO is the
  recommended algorithm.**
- **Why next:** user switched to the **position (go-to / hover)** task.

**Hover inference — the three runnable velocity policies** (T6/T7/T8, driven as position
controllers via the outer P-loop). PPO T6 is flat and tight; SAC T7 diverges under wind and
SAC T8 (tuned) still oscillates — the structural SAC instability, made visible.

![Velocity hover — T6/T7/T8](docs/fig_all_hover_velocity.png)

> T3 `results_sac` (OBS-V22), T4 `results_fs` and T5 `results_sac_fs` (88-dim frame-stack)
> predate the 29-dim RPM+wind obs and **cannot be re-run** against the current env — their
> numbers below are the historical values recorded at training time.

---

# Era 6 — Position control (T9–T16)

Task change: reach a **target position**. **OBS-P29** (relative position + velocity + R +
ω + last_action + motor_rpm + wind_est). Reward evolved a lot (below). PPO-default, `n_stack=1`.
Targets sampled at distance `Uniform(0, POS_RANGE)`, random direction, incl. near-zero.

### T9 · position, `pos_range=5 m` — stopped immediately
- User noted a 5 m range caps reachable speed at `√(a·R) ≈ √(12·5) ≈ 8 m/s` — it would never
  learn fast flight. → **`pos_range` 5 → 30 m** (reaches ~19 m/s), `speed_cap=18`.

### T10 · position, first reward → SUICIDE (stopped at 1.9M)
- **Reward (buggy):**
  ```
  dp=‖p−p_target‖, speed=‖v‖
  r = exp(−0.5·(dp/1.0)²) + 0.5·exp(−0.5·(dp/3.0)²) − 0.05·dp
      − 0.02·exp(−0.5·dp²)·speed − 0.01·max(0,speed−18)² + smooth ;  crash: −10
  ```
- **Result:** For far targets the exp terms ≈0 and **`−0.05·dp` makes r negative**. Since a
  crash *ends* the episode, the policy learned to **crash immediately** to stop accruing
  negative reward: **ep_len 25/400 steps, return frozen ≈ −25** even at 1.9M.
- **Fix → next:** add a **non-negative baseline** so alive always beats the −10 crash.

### T11 · position, suicide-fixed (Gaussian σ=1.5) · `results_pos` · 3M
- **Reward:**
  ```
  r = clip(1 − dp/30, 0, 1)              # positive baseline (guidance + survival)
    + exp(−0.5·(dp/1.5)²)                # Gaussian precision peak
    − 0.02·exp(−0.5·dp²)·speed − 0.01·max(0,speed−18)² + smooth ;  crash: −10
  ```
- **Result:** trains cleanly (ep_len→400). Hover settles at a **rock-steady 0.52 m offset**
  (calm & wind ≈0.52/0.91 m; jitter std ≈0). Cause: a Gaussian is **flat at its peak** —
  being 0.52 m off costs only **3.8%** of the reward → no pull to zero.
- **Why next:** user suggested removing the square (Gaussian → exponential) for a non-flat peak.

### T12 · position, exponential σ=0.3 · `results_pos2` · 3M
- **Reward:** same as T11 but the precision term →
  ```
  + 2.0·exp(−0.5·(dp/0.3))              # exponential, σ=0.3  (removed the **2)
  ```
- **Result:** **WORSE — hover 2.31 m** (calm) / 5.38 m (wind). σ=0.3 is **narrower than the
  achievable precision (~0.3 m)**, so the policy almost never reaches it → the bonus gives ~no
  gradient → it falls back to the weak linear baseline and wanders.
- **Lesson → next:** right *shape* (cusp), wrong *width*. Use a **reachable** width (σ≈1.0).

### T13 · position, exponential σ=1.0 + pin-point · `results_pos3` · 3M
- **Reward:**
  ```
  r = clip(1 − dp/30, 0, 1)
    + 2.0·exp(−0.5·(dp/1.0))            # exponential, reachable
    + 0.5·exp(−0.5·(dp/0.25)²)          # tiny pin-point bonus (<0.25 m)
    − 0.02·exp(−0.5·dp²)·speed − 0.01·max(0,speed−18)² + smooth ;  crash: −10
  ```
- **Result:** hover **0.61 m** calm / 0.66 m wind — about even with the Gaussian, not the hoped
  gain. But return still climbing at 3M.
- **Why next:** user said **train more** (same [128,128] net — not a bigger network).

### T14 · position, continue to 6M · `results_pos3b`
- **Reward/obs:** identical to T13. Continued from T13 (optimizer state preserved), +3M.
- **Result:** hover **0.61 → 0.19 m** calm, 0.30 m wind; step overshoot 2.56 m. **More training
  (same net) was the fix** — the 0.5 m "floor" was under-training, not capacity. (My earlier
  "fundamental floor" claim was wrong.)
- **Why next:** attack the 4 m-step **overshoot** (~2.6 m) with a stopping-distance penalty.

### T15 · position, continue to 9M + stopping-distance penalty · `results_pos3c`
- **Reward:** T13/T14 but the brake term replaced by a stopping-distance limit:
  ```
  − 0.05·max(0, speed − √(2·6·dp))²     # never exceed the speed you can brake from
  ```
- **Result:** hover improved further (**0.12 m** calm / 0.21 m wind) but the **overshoot did
  not budge (2.56 → 2.63 m)** — penalty weight too small / `a_brake=6` too optimistic, and the
  aggressive approach was ingrained.
- **Why next:** user argued the **pure reward should learn no-overshoot itself** (overshoot is
  reward-suboptimal) — test by removing the penalty and training more.

### T16 · position, continue to 12M, PURE reward · `results_pos3d` — POSITION FINAL ⭐
- **Reward (final):**
  ```
  r = clip(1 − dp/30, 0, 1)
    + 2.0·exp(−0.5·(dp/1.0)) + 0.5·exp(−0.5·(dp/0.25)²)
    − 0.01·max(0, speed − 18)²           # soft speed cap (safety) only — NO brake/stop-dist
    + smooth ;  crash: −10
  ```
- **Result:** **overshoot collapsed 2.63 → 0.33 m** and **hover → 0.06 m calm / 0.03 m wind**
  (step final err 0.024 m) — *beating* the velocity+outer-loop reference (~0.2 m). It was flat
  6M→9M then refined sharply by 12M. **The user's hypothesis held: a clean reward + enough
  training removed overshoot with no penalty.**

- **Result progression (position hover & step):**

  | steps | reward | hover calm | hover wind15 | step overshoot |
  |---|---|---|---|---|
  | 3M (T13) | exp σ1.0 | 0.61 | 0.66 | — |
  | 6M (T14) | exp σ1.0 | 0.19 | 0.30 | 2.56 |
  | 9M (T15) | + stop-dist | 0.12 | 0.21 | 2.63 |
  | 12M (T16) | pure | **0.06** | **0.03** | **0.33** |

**Hover inference — all six position policies (T11→T16), one plot.** T12's too-sharp reward
(`exp σ=0.3`) is unreachable and drifts off (2.3 m calm / 5.4 m wind); T13 (`σ=1.0`) recovers;
then pure additional training tightens hover monotonically to 0.06 m calm / 0.03 m wind. The
reward tricks (T14→T15 stop-distance penalty) did *not* move the needle — steps did.

![Position hover — T11..T16](docs/fig_all_hover_position.png)

**Circle inference — every runnable model** (position policies direct; velocity policies via
outer loop). Shows the path-tracking weakness is *general*: all position policies phase-lag a
moving reference (RMS 3.5–4.6 m, trained on static goals); velocity+loop overshoots on entry
(`Kp=1.5` too hot) then spirals in (PPO T6 best, 2.57 m). Fixing this needs moving-target
training, not more steps.

![Velocity circle — all](docs/fig_all_path_velocity.png)

![Position circle — all](docs/fig_all_path_position.png)

---

## Current saved models
- **`results_obs`** — velocity (PPO, T6): 0.82 m/s, wind-robust.
- **`results_pos3d`** — position/hover (PPO, T16): 0.06 m hover, 0.33 m step overshoot.
- **`results_sac_tuned`** — best SAC (T8), reference.

## Cross-cutting lessons
1. **Sense hidden states directly** (motor RPM, wind observer) > infer from history (T4→T6).
2. **Reward traps cost the most time:** negative-living + terminal-crash = suicide (T10);
   Gaussian flat-peak = deadband (T11); too-sharp = unreachable (T12).
3. **Reward sharpness must match achievable precision** (T11/T12/T13).
4. **More training + a clean reward beat shaping** (T13→T16).
5. **PPO > SAC under heavy DR** — SAC sample-efficient but unstable (T3/T5/T7/T8).
6. **Some limits are physical** (20 m/s into 20 m/s wind ≈ thrust envelope).
