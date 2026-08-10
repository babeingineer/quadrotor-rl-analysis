# Eliminated mechanisms — the negative-results register

Consolidated so nothing here gets re-tested. Every row was a controlled test against a stated
baseline, not an impression. Where a number is missing I say so rather than inventing one.

**Critical correction (trial 72):** continuation applied range/integral overrides after building
the environment arguments. Trials 63, 65, and 66 therefore did not train on their claimed changed
spans, and trial 61 received only one 8M stage of actual split-integral dynamics. Their earlier
“closed/refuted” labels are retracted below. See
[72_training_integrity_fixes.md](72_training_integrity_fixes.md).

**Read this with [70_reward_scale_invariance.md](70_reward_scale_invariance.md) in mind.** Several
rows below ran on a reward whose shaped gradient at speed is ~1e-6 to 1e-22. Two distinct
situations, and they deserve different weight — both marked ⚠:

- **Refuted on a fair comparison, caveat noted.** The mechanism lost to a baseline that was
  itself healthy, so the negative stands; the caveat is only that the *ceiling* both arms hit may
  have been set by the reward (e.g. 100 Hz at 3.81 vs 2.38 — a clear loss either way).
- **Comparison could not resolve the mechanism.** Both arms sat in the same gradient-starved
  regime, so the null is closer to *uninformative* than to refuting. This applies to **trial 64**
  (2.10 vs 2.03) and **trial 65** (2.48 vs 2.03): differences of a few percent between two
  fast-band policies whose shaped gradient is ~1e-6. Do not cite these as evidence the
  mechanisms are useless — cite them as evidence the fast bands do not respond to anything, which
  is trial 70's point.

## Architecture and capacity

| mechanism | trial | result vs baseline | verdict |
|---|---|---|---|
| Bigger net 512×512 | 11 | 5.55 ≈ 256×256's 5.61 | capacity was never the limit |
| LSTM / RecurrentPPO (implicit system-ID vs ±20% aero DR) | 18 | **17.20**, yaw 82° @6M vs MLP 5.26 | decisively worse; memory path closed |
| Privileged critic (asymmetric actor-critic, critic sees the hidden draw) | 30 | 5.13 median vs 3.67 | advantage-noise hypothesis refuted |
| Relative-attitude obs (`att_rel`) | — | implemented, rejected on measurement | no gain |
| True airflow observability (`air_obs`, body-frame airflow in obs) | — | no gain | the policy already infers what it needs |

## Reward shaping

| mechanism | trial | result vs baseline | verdict |
|---|---|---|---|
| Precision peak **weight** 0.7 → 1.5 | 31 | 3.67 ≈ 3.67 | flat — and **now explained**: scaling a term whose value is 1e-22 at speed leaves it 1e-22 ⚠ |
| Coverage width 12.5 → 5 | 12 | 5.44 vs 5.55 | small real gain (adopted, not eliminated) |
| Reward sharpening past trial 12 | — | ~0.2/iteration, plateaus | absolute-width shaping exhausted at ~5 m/s ⚠ |

## Observation dynamics / memory

| mechanism | trial | result vs baseline | verdict |
|---|---|---|---|
| True integrator (leak τ → ∞) — attempt 1, bundled | 22 | 2.66 mean / 2.08 median vs 0.82 | failed, but 4 variables at once — inconclusive by design |
| True integrator — isolated | 25 | velocity 0.93 ≈ 0.82 (exonerated) but yaw 90° at γ0.99 | γ was never the yaw driver |
| Split integral leak (yaw τ decoupled) — fresh lineage | 56 | 6.01 @12M | inconclusive: my design error, launched fresh right after 54 closed fresh training |
| Split integral leak — on the champion | 61 | stage a trained old τ=3 but evaluated τ=30; stage b reached 2.72 [2.25–3.07] after 8M of actual τ=30 adaptation vs **2.03** | negative at 8M, but the claimed 16M test was false; **REOPENED / not fully resolved** |

## Control rate and inner loop

| mechanism | trial | result vs baseline | verdict |
|---|---|---|---|
| 100 Hz policy rate (first attempt) | 36 | worse — but confounded by my own `gae_lambda`/`n_steps` left in step units | invalid test, user caught it |
| 100 Hz policy rate (fair retest, flags added) | 39 | **3.81 vs 2.38** | refuted on a fair test |
| Stiff inner loop (kp 40 / ki 10) | 19 | 8.94 | ripple is real (~1 m/s) but not dominant |
| Increased control authority | 38, 40 | no gain | refuted twice |

## Domain randomization and identification

| mechanism | trial | result vs baseline | verdict |
|---|---|---|---|
| Aero DR **off** (train without ±20% aero uncertainty) | 20 | **11.40 vs 8.94 with DR** | identification refuted as the bottleneck; DR even regularizes |
| Wind curriculum (staged wind) | 03 | no effect | staging doesn't fix incentives |
| Training at the real wind spec 0–15 (vs 0–20) | 11 | 6.70 → 5.61 | real gain (adopted) — the 0–20 default embedded corners the aircraft never faces |

## Curriculum and initialization

| mechanism | trial | result vs baseline | verdict |
|---|---|---|---|
| Tough-init (failure-state starts) alone, for tracking | 03 | 0/60 recoveries after 2.4M dive-start steps | exposure alone cannot beat a reward barrier |
| Tough-init vs the yaw gate (ablation) | 06 | 7.89 gate-only ≈ 7.36 with both | **the gate is the active ingredient**; tough-init dropped |
| Trim-init dose 0.2 → 0.4 | 28 | 4.64 ≈ 4.09 | exposure saturated |
| Refined (per-episode) trim-init, fresh lineage | 54 | 5.07 @12M vs 2.03 transfer | fresh fast-band training is a dead end ⚠ |
| Refined trim-init on the champion | 57 | 2.50 vs 2.03 | trim-init fully exhausted at 18–25 |
| Tough-init dose for **recovery** (0.10, 0.20) | 69 | recovery 12→13→22%, precision 0.82→0.89→**0.97** | works at a bad exchange rate; routing beats it |

## Span, lineage, and further training at the fast bands

| mechanism | trial | result vs baseline | verdict |
|---|---|---|---|
| Narrowing the span to the band (25–34) | 63 | 5.06 [4.28–6.45] vs **3.77**, but training remained 21–34 | **INVALID TEST**: narrowing was written to config/eval but never applied to that training stage |
| Scaffold-width rule applied at 18–25 (train 14–25) | 65 | 2.48 [2.08–2.88] vs **2.03**, but training remained 18–25 | **INVALID TEST**: width change never entered the training env |
| Scaffold-width rule at 25–34 (train 20–34) | 66 | 5.06 [4.25–6.02] vs **3.77**, but training remained 21–34 | **INVALID TEST**: width change never entered the training env |
| Patient low-LR ladder at 18–25 | 64 | 2.10 vs 2.03 | NULL — the band is not step-size limited ⚠ |
| Further training at the fast bands | 62–66 | extra training from propagated final checkpoints often made them worse, but several claimed span changes never occurred | evidence of drift under the legacy reward, **not** evidence that every span or continuation from a paired best checkpoint fails |

## Action-interface changes (single-policy campaign, trials 77-81)

| mechanism | trial | result vs baseline | verdict |
|---|---|---|---|
| Full-sphere attitude command (`att_tilt_max=120`, linear \|xy\|→tilt) | 78 | **14.90 vs xw77's 4.25** at 32M; hover 3.7x worse, low 4.3x worse | **REFUTED** — rescaling the map halves resolution everywhere. The 80 deg cap is real, but this way of lifting it is strictly harmful. Any retry must preserve low-tilt resolution |
| Command-scaled velocity-error obs (`rel_obs`) | 79 | pooled neutral (4.17 vs 4.25) BUT hover **2.01 → 0.74, 0% → 67% <1**, low 2.08 → 1.45 | **ADOPTED** — mechanism confirmed at the slow end; the pooled median averaged it away. Fast bands ~10% worse, within single-seed noise |
| Resolution-preserving tilt extension (`att_tilt_ext=120`) | 81 | — | **NOT RUN** (stopped by directive). Cap hypothesis remains untested |

## Teacher / hybrid approaches

| mechanism | trial | result vs baseline | verdict |
|---|---|---|---|
| PID-teacher **distillation** | — | teacher itself is worse than RL above 18 m/s | cannot distil a worse policy into a better one |
| PID-teacher **initialisation** (BC-init, then RL) | 76 | head-to-head on one stratified γ protocol: descents mid **4.15 vs RL 1.83**, vhigh **16.19 vs RL 10.16**; climbs also worse | **refuted separately from distillation** — a genuinely different proposal (bootstrap, not final answer), but the teacher is worse than the student at every band/direction tested, so BC-init starts BELOW where RL converges. Caveat: the teacher IS 3.8× more precise at mid on the ~60% of draws where its fixed gains stay stable |
| Residual RL | — | rejected by user constraint (*"i don't want residual RL. i want full RL"*) | not tested |
| Trim feedforward (`trim_ff`, deployable variant) | 67, 68 | **cancelled by user** mid-run (*"i don't need trim. i need only pure RL."*) | implemented, left default OFF, never evaluated |

## What actually worked (for contrast)

1. **Elevons** (02): 81.7 → 41.3. Motor torque is constant with airspeed; aero moment grows with
   V². Only control surfaces (also V²) keep pace.
2. **Yaw gate** (04): 41.3 → 9.2. The breakthrough. A stable dive *earned* +1.4/step from an
   always-on yaw reward; gating yaw by velocity success destroyed that equilibrium.
3. **Attitude gate** (08): released yaw in wing-borne flight, where the nose is slaved to the
   velocity vector and a commanded yaw is physically unsatisfiable.
4. **Attitude-setpoint action interface** (`att_cmd`, 32): structurally stabilizes the unstable
   wing-borne trim instead of asking the policy to do it — first sub-1 band.
5. **Trim-init** (27): biggest single gain at speed. Trial 70 reframes *why*: it starts episodes
   inside the only region where the shaped reward is still numerically alive.
6. **Convergence ladders** (16, 33): the same recipe simply run longer, CI-gated per stage.
7. **Supervisory recovery switch** (69): pooled recovery 22% → 46% with no median cost — routing
   over two trained nets, not retraining.

## The one recurring failure mode (found 4×)
**Every plateau traced to a reward term that pays comfortably inside the failure regime:**
dive + full yaw payout (04) → half-tilt + yaw payout (08) → loitering + 75% coverage payout at
9.5 m/s error (12) → **loitering because the velocity reward is numerically zero at speed (70)**.
The diagnosis that worked every time is per-step reward accounting of the observed behaviour vs
the desired one. Trial 70 adds a corollary: **also evaluate the reward numerically at the edges
of the commanded range** — six trials blamed capacity, memory, or interference before anyone
checked whether the objective was still finite out there.

## Descent-asymmetry mechanism hunt (trial 71, evaluation only — no training)
The fast-band residual turned out to be a descent/climb asymmetry (up to 4.2× at matched speed,
all four bands). Five candidate causes, all eliminated by measurement:

| candidate | test | verdict |
|---|---|---|
| Physically infeasible commands | re-solve trim per DR draw (±20% aero, mass 13.6–14.1) | **refuted** — infeasible ~0% at every (V, γ) |
| Thrust floor at descent (T≥0 boundary) | per-draw throttle-at-floor rate | **refuted as primary** — 17–42% at γ=−40 but 0% at γ=−20, which predicts a cliff; measured profile is a smooth ramp, and level flight (4.88) is 2× harder than a +40° climb (2.02) with 90–137 N margin at both |
| Required trim tilt ("error doubles every 16°") | within-policy low band, where tilt is constant 2.4–3.9° across all nine angles | **refuted** — 2.08× error spread at constant tilt. The +0.774 correlation was worthless: tilt is monotone in both speed and γ, so beating each marginal is near-automatic, and the tilt values themselves are solver noise (non-monotonic in γ at V=16) |
| Settling time from a hover start | 20 s vs 8 s episodes | **refuted** — gap slightly WIDER at 20 s (4.8× vs 4.2×) |
| Entry (can't get into a descent) | trim-start hold test (start AT the commanded velocity) | **refuted → it is STABILIZATION**: 6.83× gap when placed in the state, worse than from rest |

Untested candidate left standing: a **learned aversion to descending**, installed by the early
anti-dive work (trials 01–04, where the yaw gate destroyed a dive attractor and delivered the
campaign's biggest single win). Consistent with the policy *departing* a feasible, better-paying
descent, but separating it from "descents are simply harder to stabilize" requires training.
