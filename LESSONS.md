# Lessons Learned — the deep version

Everything we learned across the ~16 training runs in
[TRAINING_HISTORY.md](TRAINING_HISTORY.md) (RL control of a heavy, domain-randomized
quadrotor). For each lesson: the **principle**, the **mechanism/math** behind it, the
**exact evidence** from our runs, the **root cause**, the **fix and why it works**, and the
**caveats / when it does *not* apply**. Run IDs (T#) point back to the history.

> Task context these lessons come from: a ~10 kg quad, 4×40 N motors, **per-episode**
> randomization of mass (9–11 kg), wind (0–20 m/s), and motor lag (τ 0.1–0.25 s); a PID
> attitude-rate inner loop; episodes **terminate on crash** (tilt > 85°); PPO & SAC in
> Stable-Baselines3, on CPU. Keep that context in mind when generalizing.

---

## Contents
1. [PPO vs SAC](#1-algorithm-choice--ppo-vs-sac-deep-dive)
2. [Reward design](#2-reward-design--where-most-of-the-work-was)
3. [Observations & partial observability](#3-observations--partial-observability)
4. [Training dynamics](#4-training-dynamics)
5. [Control architecture](#5-control-architecture)
6. [Sim realism & domain randomization](#6-sim-realism--domain-randomization)
7. [Physical vs learnable limits](#7-physical-vs-learnable-limits)
8. [Engineering & debugging](#8-engineering--debugging)
9. [Meta-lessons](#9-meta-lessons)

---

## Cheat-sheet (read this if nothing else)

| Situation | Do this | One-line why |
|---|---|---|
| heavy domain randomization + crash-termination | **PPO** | SAC destabilizes; PPO stays monotone |
| fast/parallel sim + CPU (env steps cheap) | **PPO** | wins wall-clock *and* quality (SAC is gradient-bound) |
| env steps are the scarce resource (real hardware / very slow sim), + GPU | **SAC** (tuned) | ~4× fewer env steps — but only helps if steps cost more than gradients |
| any task that **terminates on failure** | reward **≥ 0 while alive** | else the agent suicides to stop losing reward |
| want tight steady-state precision | reward gradient **non-zero at the goal** (exp/Laplacian, not Gaussian) **and reachable** | flat peak → deadband; too-sharp → unreachable |
| stuck at a precision "floor" | **train 2–4× longer** before blaming capacity | floors break late |
| tempted by a behavior-shaping penalty | try **clean objective + more steps** first | pure reward often learns the behavior |
| hidden state hurts a memoryless policy | **measure/estimate it and feed it in** | direct sensing > history inference |
| adding actuator lag | **lower inner-loop gains** | lag eats phase margin |
| deploying with **moving/changing setpoints** | use **target-independent** features (disturbance observer, not error-integral) | integrals pollute on setpoint changes |
| failures persist after good training | check if it's a **physical (thrust) limit** | RL can't beat physics |

---

## 1. Algorithm choice — PPO vs SAC (deep dive)

### Principle
For **continuous control under heavy per-episode domain randomization, with episodes that
terminate on failure**, prefer **PPO**. SAC is more sample-efficient but tends to
**destabilize** in this regime. This is a *conditional* rule, not "PPO > SAC" in general.

### Mechanism — why off-policy struggles under heavy DR
- **On-policy (PPO)** learns only from fresh rollouts of the *current* policy, and its clipped
  surrogate objective caps how far the policy moves per update (a soft trust region). So even
  when episodes are wildly heterogeneous (different mass/wind/lag each time), each update is a
  small, well-scoped step → **monotone, stable** improvement.
- **Off-policy (SAC)** reuses a **replay buffer** that, under per-episode randomization,
  contains transitions from many *different dynamics* **and** from *older policies*. The twin
  Q-networks must regress a value target that is (a) non-stationary (policy moving), (b)
  bootstrapped (moving target network), and (c) drawn from a heterogeneous mixture. That's a
  recipe for **value overestimation → policy exploitation of the overestimate → collapse**.
  Add auto-tuned entropy (α changing during training) and it gets less stable still.

### The instability signature we saw (every SAC run)
Return **rises fast, peaks early, then drifts down**:
- T3 (untuned): peak ~399 @250k → drifted.
- T7 (untuned, better obs): still 4.09 m/s error, 18% crash.
- T8 (tuned): peak ~468 @250k → bounced down to ~279 by 800k.
The *best checkpoint* was salvageable (that's what we evaluated), but you cannot just "train
longer" — more steps made it worse, not better.

### Evidence (velocity task, 50 identical scenarios)
| | PPO (T6) | SAC untuned (T7) | SAC tuned (T8) |
|---|---|---|---|
| mean steady error | **0.82 m/s** | 4.09 | 1.48 |
| crash rate | **0%** | 18% | 2% |
| env steps | 3M | 500k | 800k |
| **wall-clock (CPU)** | **~32 min** | ~62 min | ~72 min |
| **throughput** | **~1590 steps/s** | ~135 | ~135 |

Tuning improved SAC **2.7×** (T7→T8) but did not overtake PPO.

### Sample efficiency ≠ training speed (important caveat)
SAC used **~4× fewer environment steps** than PPO — but was **~2× slower in wall-clock**
(72 vs 32 min) and had **~12× lower throughput** (135 vs 1590 steps/s). Why: SAC is
**gradient-bound** — it does a gradient update (twin critics + actor + entropy) essentially
every transition, which on CPU dominates. PPO is **simulation-bound** — it collects rollouts
across 6 parallel env workers, then does a burst of cheap batched updates. So on a
**fast/parallel sim with CPU compute, PPO wins wall-clock *and* quality**, and SAC's fewer
steps buy nothing.

**Sample efficiency only becomes an advantage when *environment interaction* is the expensive
resource** — e.g. training on **real hardware** (each step is seconds of real flight + reset)
or a **very slow simulator** — where minimizing env steps outweighs the per-step gradient
cost. A **GPU** also shifts the balance (it makes SAC's gradient steps cheap, shrinking or
flipping the wall-clock gap). On our setup (cheap parallel sim, no GPU), neither held, so
**PPO was strictly better** — faster *and* more accurate.

### What each SAC knob did, and why (ranked by impact)
1. **Learning rate 3e-4 → 1e-4 (biggest):** slows the Q→policy feedback loop that drives
   overestimation/collapse. Directly attacks the drift-down.
2. **gSDE on (big):** state-dependent, temporally-correlated exploration instead of independent
   per-step noise → **smoother action trajectories → fewer exploration crashes → cleaner replay
   buffer** (less crash-data poisoning the Q-targets).
3. **gradient_steps 4 → 2 (lower update-to-data ratio):** high UTD compounds overestimation in
   off-policy learning without special regularization (REDQ/dropout); halving it stabilizes.
   Bonus: fewer gradient steps → faster wall-clock.
4. **batch 256 → 512:** lower-variance gradients.
5. **net [128,128] → [256,256]:** more capacity for the randomized value function (secondary).

### Decision framework
- **Use PPO when:** heavy randomization, sparse/terminal failure, you want "it just works"
  stability, and env steps are cheap (fast sim, parallelizable).
- **Use SAC when:** **environment interaction is the scarce resource** (real hardware, or a
  very slow sim) *and ideally you have a GPU*, randomization is mild-to-moderate, and you can
  invest in tuning (lr↓, gSDE, low UTD, maybe target-entropy). Its sample efficiency (~4×
  fewer env steps here) is real — **but it only translates to faster training when a step
  costs more than a gradient update.** On our cheap parallel sim + CPU it did *not*: SAC was
  ~2× slower in wall-clock despite fewer steps (see caveat above). Don't reach for SAC's
  sample efficiency unless env steps are genuinely your bottleneck.

### Caveats / honesty
- This is **not universal.** On standard, low-randomization benchmarks (e.g. MuJoCo) SAC often
  **matches or beats** PPO and is far more sample-efficient. Our result is specific to *heavy
  DR + crash termination + a CPU/untuned budget*.
- We did **not** exhaustively tune SAC (no target-entropy schedule, no REDQ/CrossQ). A
  determined SAC effort might close more of the gap. The point is **PPO needed no such effort.**

---

## 2. Reward design — where most of the work was

More of our failures came from reward design than from anything else. Four sub-lessons.

### 2a. Never let a crash-terminating task have net-negative "living" reward
**Principle:** if every step yields negative reward and a **crash *terminates*** the episode,
the return-maximizing behavior is to **crash as fast as possible**.

**The math (return accounting).** Our first position reward (T10) was ≈ `−0.05·dp` far from
the target (the Gaussian bonuses were ~0 for targets up to 30 m away). Compare two strategies
for a target `dp≈18 m` it can't quickly reach:
- **Survive** the 400-step episode: return ≈ `−0.05·18·400 ≈ −360`.
- **Crash at step ~10:** return ≈ `−0.05·18·10 + (−10) ≈ −19`.

`−19 ≫ −360`, so **crashing is ~20× better**. And scaling the reward doesn't fix it: with the
fixed `−10` crash penalty, crashing beats surviving whenever `0.05·d·400 > 10`, i.e. for any
sustained error `d > 0.5 m`.

**What we observed (T10):** episodes collapsed to **25 of 400 steps**, return frozen at
**≈ −25**, *no* learning even at 1.9M steps. Classic reward-hacking via early termination.

**Fix and why it works:** add a **non-negative baseline** so being alive always beats the
crash penalty. We used `clip(1 − dp/R, 0, 1) ∈ [0,1]`. Now surviving a far target earns ≥ 0
per step ≫ −10, so the policy prefers to fly. Episodes immediately went to 400 steps.

**Generalize:** any task with terminal failure states — keep per-step reward ≥ 0 while alive,
*or* make the crash penalty larger than the worst-case remaining survivable return (fragile),
*or* use `truncation` instead of `termination` so future value bootstraps (changes semantics).
The positive-baseline is the clean choice.

### 2b. Reward sharpness must match the *achievable* precision
**Principle:** the width of the reward's peak has to sit in the band the controller can
actually reach. Two failure modes bracket it:

- **Too flat → deadband.** A **Gaussian** `exp(−½(d/σ)²)` is *flat at its own peak*: its
  gradient at `d=0` is **0**. With σ=1.5 m (T11), being 0.5 m off cost only **3.8%** of reward
  → **no gradient to null the last half-meter** → the policy parked at a rock-steady **0.52 m
  offset** (measured jitter ≈ 0; it was a stable deadband, not noise).

- **Too sharp → unreachable → ignored.** Shrinking to an **exponential σ=0.3** (T12) put a
  strong gradient at 0, *but* the bonus was only meaningful within ~0.3 m — **narrower than
  the drone's ~0.3 m achievable precision** (motor lag + wind + mass). During training the
  policy almost never entered that band, so the term contributed ~no gradient, the policy fell
  back to the weak linear baseline, and hover got **worse: 2.31 m**. *A reward you can't reach
  is a reward you can't learn from.*

- **Just right → reachable + non-flat.** An **exponential σ=1.0** (T13+) has a **cusp** at the
  target (non-zero gradient `−1/(2σ)` at `d=0`, unlike the Gaussian's 0) over a *reachable*
  ~2 m band. Combined with more training this reached **0.06 m** (T16).

**Shape math (why exponential > Gaussian for precision):**
`d/dt exp(−½(d/σ)²)|₀ = 0` (flat peak) vs `d/dt exp(−½·d/σ)|₀ = −1/(2σ) ≠ 0` (cusp). The cusp
keeps pulling toward zero; the Gaussian gives up near zero.

**Concrete numbers (hover error by reward, position task):**
| reward precision term | hover (calm) |
|---|---|
| Gaussian σ=1.5 (flat peak) | 0.52 m |
| exponential σ=0.3 (unreachable) | 2.31 m |
| exponential σ=1.0 (reachable cusp) + training | 0.06 m |

**Generalize:** pick σ ≈ the precision you can realistically hit; use a cusped kernel
(exp/Laplacian, or L1) when you want tight steady-state; add a tiny even-sharper "pin-point"
bonus only as a *secondary* term (it's sparse, so it must not be the primary gradient).

### 2c. Shape the *objective*, not the *behavior* — and try that first
**Principle:** encode *what you want* (be at the target), not *how to move* (speed limits). A
well-posed objective usually makes the desired behavior optimal, so the policy discovers it.

**Evidence:** the position policy overshot a 4 m step by ~2.6 m. We added a physically-motivated
**stopping-distance speed penalty** (`−w·max(0, v − √(2a·dp))²`) to force deceleration (T15) —
and it **did not help** (overshoot stayed 2.6 m). Removing it and simply training the **clean
position reward** longer (T16) **eliminated the overshoot (→0.33 m)**, because overshooting is
inherently reward-suboptimal (time spent past the target is time off-target). The behavior
emerged from the objective without being hand-coded.

**Caveat:** shaping is legitimate when the pure reward's signal is too sparse/weak to learn in
budget. But reach for *information + training* before *behavioral penalties* — penalties add
bias and often don't bite anyway.

### 2d. Keep a dense far-field gradient
A pure Gaussian/exponential **saturates to ~0 far from the target** → no learning signal when
you're far. Always add a term with gradient over the whole range: a linear `−k·d`, or a
`clip(1 − d/R, 0, 1)` baseline. This baseline also doubled as the survival term in 2a.

**The general reward recipe we converged on:**
```
reward =  positive_baseline_with_far_field_gradient       # survival + coarse guidance
        + reachable_cusped_precision_term                  # tight steady-state pull
        (+ optional tiny pin-point bonus)                  # last-cm, secondary
        + small smoothness penalties (‖ω‖², ‖Δaction‖²)    # anti-jitter
        − large one-time penalty on terminal failure
```

---

## 3. Observations & partial observability

### 3a. *Sense* hidden states; don't make the policy *infer* them
**Principle:** if a hidden variable governs the dynamics (actuator spin-up, wind), and you can
measure or estimate it, **put it in the observation** rather than forcing a memoryless net to
infer it from a history window (frame-stacking) or a recurrent state.

**Mechanism:** adding the hidden state restores the **Markov property** — the same observation
now maps to the same dynamics. Frame-stacking only lets the net *estimate* the hidden state
from N past frames (noisy, delayed, limited horizon); a direct measurement is exact and
instantaneous.

**Evidence:** motor lag + wind, velocity task —
- Frame-stack (n_stack=4, infer from history), T4: **1.74 m/s**.
- Direct: motor RPM (ESC) + wind estimate, T6: **0.82 m/s, 0% crash**.
Same net, same reward — the observation change alone roughly halved the error.

### 3b. Use a disturbance observer (physics-based feature engineering)
**Principle:** estimate an unmeasured *force* disturbance from the equations of motion, and
feed the estimate in.

**Mechanism:** Newton's second law solved for the unknown:
```
m·a = F_thrust + F_gravity + F_wind
⇒ F_wind ≈ m·a − R·[0,0,T] + [0,0, m·g]
```
Using **nominal** mass and the **commanded/achieved** thrust — exactly what an onboard
estimator has. On real hardware the IMU's specific-force reading gives this even more directly
(`F_wind_body ≈ m·a_imu − [0,0,T]`).

**Why feed the observer, not raw acceleration?** Two reasons: (i) it's exact physics
feature-engineering (the net doesn't have to *learn* `m·a − thrust + g`), and (ii) it's
**EMA-filtered** — a *memoryless* MLP can't filter noisy instantaneous acceleration itself, so
the observer supplies the temporal smoothing the policy lacks.

**Evidence:** the observer recovered the true wind force to ~0 N (verified), and made the
policy **wind-robust**: strong wind (>14 m/s) tracked as well as calm (1.48 vs ~0.9 m/s error),
and hover in 15 m/s wind reached 0.03 m (T16).

### 3c. Prefer *target-independent* state features → they transfer to changing setpoints
**Principle:** if you'll deploy with moving/real-time targets, use features whose meaning
doesn't depend on the setpoint being constant.

**The trap (why we did *not* use a velocity/position-error integral for wind):** an integral
`∫(target − state)dt` cancels a **constant** disturbance beautifully **if the target is
constant**. But with a **changing** target it accumulates the **setpoint-transient error** too
→ windup and wrong compensation right after every target change. A **disturbance observer**,
by contrast, is computed purely from the force balance (§3b) — `target` appears nowhere — so it
reads the same whether the target is fixed, ramping, or jumping. **Same job (reject wind),
only the observer transfers.**

### 3d. Include whatever makes the MDP Markov for *your* controller
- Actuator lag → include **actuator state** (motor RPM).
- Position controller → include **velocity** (needed to plan deceleration; without it, it
  overshoots blindly).
- Attitude → prefer a **rotation matrix** (9) over Euler angles (gimbal-free, no wraparound).

### 3e. Condition the inputs
Normalize each block; keep the **decision-critical** quantity well-scaled and near zero at the
goal (we fed `vel_err/20`, `rel_pos/R`, `ω/ω_max`, etc.), and still wrap with `VecNormalize` as
a safety net. Poorly-scaled obs slow or destabilize learning.

---

## 4. Training dynamics

### 4a. Plateaus can break *late* — don't declare a "floor" prematurely
**Evidence:** position hover was ~0.5–0.6 m at 3–6M and I explicitly called it a "fundamental
function-approximation floor." It wasn't: with more steps it went **0.19 (6M) → 0.12 (9M) →
0.06 m (12M)**, and step **overshoot was flat 2.56→2.63 from 6M→9M then collapsed to 0.33 m by
12M**. Late-stage refinement is real in RL (the policy sharpens fine behavior on top of coarse
behavior it learned first). **Rule:** before attributing a limit to capacity/architecture,
2–4× the training budget and re-check.

### 4b. More steps (same net) often beats a bigger network
The precision gains here came entirely from **more training on `[128,128]`**, not from
widening. Reach for compute-on-the-same-model before adding parameters — bigger nets also add
variance and slow throughput.

### 4c. Continue training with a swapped reward instead of restarting
**Principle:** if only the **reward** changes (obs/action spaces unchanged), you can **resume**
from a checkpoint (weights + optimizer state) rather than restart — reusing the expensive
learned behavior.

**Mechanism/caveat:** the critic and reward-normalization are calibrated to the *old* reward,
so expect a **brief re-adaptation dip**, then recovery. Keep the reward change modest for the
continuation to be productive (a large change ≈ retraining). We did this three times (T14–T16),
each +3M, reusing 6–9M of prior flight skill. **An observation-space change, however, requires
a fresh run** (the input layer changes).

### 4d. Eval is high-variance under DR — don't over-read the curve
Each eval = a handful of episodes over *randomly drawn* scenarios (mass/wind/target), and our
returns are **bimodal** (track ≈ +450, crash ≈ 0). So the eval mean swings with *which
scenarios were drawn*, not just policy quality — much of "SAC bouncing" was measurement noise.
**Fixes:** fix the eval seeds each evaluation, and/or use more eval episodes, to see the *true*
trend. Judge policies on a **fixed** scenario set (we compared on identical seeds).

### 4e. Task ranges set emergent behavior — choose them deliberately
For an end-to-end position policy, the **target range sets the max speed** it ever experiences:
peak speed to reach-and-stop over distance `R` is `≈ √(a·R)`. Range 5 m → ~8 m/s (T9, too
slow); range 30 m → ~19 m/s. The *reward and randomization ranges are design parameters*, not
afterthoughts — they define the behavior distribution the policy optimizes over.

---

## 5. Control architecture

### 5a. Inner-loop bandwidth vs actuator lag; retune gains when lag appears
**Principle:** a fast inner loop (rate PID @500 Hz) only works if the actuator is fast relative
to it. A **100–250 ms** motor lag is 5–12× the 20 ms policy step and 50–125× the 2 ms PID step
→ it **shrinks the achievable inner-loop bandwidth** and **eats phase margin**. Our original
high gains (`kp=12`) oscillated once lag was added; we **lowered to `kp=6`** (and re-verified
step-response stability at worst-case τ=0.25 s). **Rule:** adding actuator lag ⇒ reduce
loop gain (or you get oscillation), and don't expect the loop to track faster than ~1/τ.

### 5b. End-to-end learned control vs the classic cascade — a real trade
- A **learned position policy** *can* match/beat an exact outer P-loop on precision given
  enough training: **0.06 m hover vs ~0.2 m** for velocity-policy + hand-tuned P-loop (T16).
  Why it can win: the learned policy uses the disturbance observer directly (no
  proportional-controller steady-state error), and it learns the full accel→decel profile.
- But the **cascade** (velocity policy + outer position loop) is **simpler, interpretable,
  tunable, and decouples speed from range** (the velocity policy natively covers 0–20 m/s; the
  outer loop just clamps the commanded speed). The end-to-end policy **couples speed to range**
  (§4e) and needed ~12M steps to get precise.
- **Guidance:** cascade for fast bring-up and explicit speed control; end-to-end when you want
  a single self-contained policy and can afford the training.

### 5c. Train on the deployment distribution
A position policy trained only on **static** targets **lags moving** targets (it traced an
undersized, phase-lagged circle). If you'll track dynamic paths, **train on moving targets**
(resample mid-episode / follow velocity profiles). Distribution mismatch shows up exactly where
you didn't train.

---

## 6. Sim realism & domain randomization

- **Model the disturbances that matter** and nothing spurious: first-order actuator lag,
  relative-airspeed wind drag, mass/inertia DR. **Zero PyBullet's default linear/angular
  damping** so the disturbance you *model* is the only aero force (hidden damping silently
  changes the task).
- **Use nominal (not ground-truth) mass in the onboard observer.** That's what real hardware
  has; the mass error then appears *as part of the estimated disturbance*, which the policy
  learns to compensate. Training on privileged truth you won't have at deploy is a **sim2real
  trap** — keep the policy's inputs to what a real drone can compute.
- **Randomize per-episode for robustness**, but budget for it: heavy DR is exactly what
  destabilizes off-policy learning (§1) and what makes eval noisy (§4d).

## 7. Physical vs learnable limits

**Principle:** before trying to train through a persistent failure, decide whether it's a
**sensing/control** limit (fixable) or a **physical** one (not).

**Evidence:** once wind was *observable* (§3b), wind-robustness was solved — the residual
failures were **high-speed targets into strong wind**, which is a **thrust-envelope** limit:
holding 20 m/s into a 20 m/s wind ≈ 40 m/s relative airspeed → `0.08·40² ≈ 128 N` drag + 98 N
weight ≈ **160 N**, exactly the motor budget. No reward or algorithm creates thrust you don't
have. The only fixes are **more thrust** or **a smaller demanded envelope** (don't command
infeasible setpoints; degrade gracefully). Diagnosing this saved us from "training harder" at a
wall.

## 8. Engineering & debugging

**Framework gotchas that produced impossible-looking numbers — check these first when a result
makes no sense:**

1. **Wrapper ordering with off-policy buffers.** `VecFrameStack(VecNormalize(env))` crashed SAC:
   the replay buffer was sized for the **stacked** obs but received the **un-stacked** original
   obs from `get_original_obs()`. **Fix:** `VecNormalize` on the **outside** of `VecFrameStack`
   for off-policy. (On-policy PPO was unaffected.)
2. **Subclass attribute overwritten by the base class.** We set `self.DRAG_COEFF` in the
   subclass; the base env's URDF parser then **overwrote it**, zeroing wind. Symptom: wind had
   no effect. **Fix:** rename to a non-colliding attribute (`WIND_DRAG`). *Grep the base class
   for your attribute names.*
3. **VecEnv auto-reset corrupts the last logged sample.** After `done`, `DummyVecEnv` resets
   immediately, so the final `pos`/`info` you read is the *new* episode's — our "0.00 m final
   drift" was an artifact. **Fix:** read the terminal value from `info["terminal_observation"]`
   or ignore the last sample.

**Methodology that paid off:**
- **Verify the inner loop empirically before RL** — step-response + sign checks on the rate PID
  and mixer (command +roll-rate, confirm it rolls the right way and converges) caught bugs the
  policy would otherwise have to fight.
- **Sanity-check every new observation feature** — we confirmed the disturbance observer
  recovers the true wind force (~0 N error) before trusting the policy to use it.
- **Compare on fixed scenario sets** (identical seeds) so numbers are actually comparable.
- **Watch `ep_len_mean`** as a health signal — it dropping to ~25/400 instantly exposed the
  suicide reward (§2a) long before the return plot would have "explained" it.

---

## 9. Meta-lessons

1. **Most of the "RL problem" was reward and observation design, not the algorithm.** Getting
   the reward non-pathological (§2a), matched-sharpness (§2b), and the right *sensed* quantities
   into the observation (§3) moved the needle far more than PPO↔SAC.
2. **Feed more information and train longer before reaching for clever tricks.** Direct sensing
   (T6: 1.74→0.82) and more steps (T16: 0.5→0.06 m, overshoot 2.6→0.33) beat every reward-shaping
   penalty we tried.
3. **Diagnose before iterating.** The wins came from *understanding the mechanism* — the suicide
   return-math, the flat-peak gradient, the thrust envelope — not from random reward tweaks. Two
   of our biggest time sinks (T12 too-sharp, T15 useless penalty) were tweaks made *before*
   understanding; the fixes came *after* diagnosing.
4. **Be willing to be wrong fast.** I called a "fundamental floor" that was just under-training,
   and proposed a penalty that wasn't needed. Cheap experiments (continue-training, fixed-seed
   eval) settled each question in one run instead of an argument.
