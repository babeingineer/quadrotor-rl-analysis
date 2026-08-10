# Trial 75 — the fast-band deficit is a DESCENT/TILT asymmetry, not a speed limit

**STATUS: ANALYSIS ONLY (evaluation of existing checkpoints). NO TRAINING** — user directive
stands. Every number here comes from re-evaluating trained policies and from the trim table.

**Numbering note:** first written as "trial 71" before I noticed trials 71–74 already existed
(checkpoint audit, integrity fixes, the reward ablation, and its replication). Renumbered to 75.

**Relationship to trial 73.** Trial 73 ran the matched reward ablation this analysis's predecessor
(trial 70) argued for, and promoted the `basin` arm: worst-band median 18.93 vs legacy 32.48. Yet
**every arm scored 0% of episodes below 1 m/s.** So the reward fix demonstrably moves the fast
bands and still leaves them far from the goal. This trial identifies what the reward fix does not
touch: **the policies cannot hold commanded descents**, which is half of every band's targets.

## Why — a contradiction in my own trial-70 story
Trial 70 argued the wide-range failure is a reward that goes numerically dead at speed. Checking
that against the *trained* policies immediately complicated it: for each band champion I computed
the reward available at its own converged operating point.

| band | achieved median err | reward there | reward at 0 | unclaimed | local &#124;dr/dd&#124; |
|---|---|---|---|---|---|
| low 1–10 | 0.44 | 1.970 | 2.700 | 0.730 | 1.24 |
| mid 10–18 | 0.77 | 1.665 | 2.700 | 1.035 | 0.72 |
| high 18–25 | 1.77 | 1.202 | 2.700 | 1.498 | 0.34 |
| vhigh 25–34 | 5.73 | 0.458 | 2.700 | **2.242** | 0.14 |

The unclaimed reward is **largest** at vhigh, and the reward is **convex** there — the marginal
payout *rises* as error shrinks (0.137 at d = 5.73 → 0.543 at d = 1 → 1.090 at d = 0.5). So at
the fast bands' actual operating point the objective is alive and pointing the right way; the
policy is declining a large, increasing payout. **Trial 70's dead zone is the far-field approach
(d ≈ V at episode start), not the converged residual.** That correction matters: `rel_approach`
may help a policy *reach* fast targets, but nothing here says it would fix the fast-band
residual. Something else is binding.

## What is actually binding: descents
The vhigh error distribution is **bimodal**, not uniformly mediocre (p10 1.38, p25 2.30, p50
5.73, p75 13.18, p90 18.79), and it is essentially **uncorrelated with commanded speed**
(r = +0.09) — so it is not a thrust or speed ceiling. Sorting episodes by what actually differs:

| feature | GOOD (<3) mean | BAD (>10) mean | corr w/ err |
|---|---|---|---|
| **climb angle γ** | **+31.8°** | **−36.4°** | **−0.403** |
| direction error | 2.0° | 16.8° | +0.704 |
| vertical error | 0.08 | **+6.10** | −0.254 |
| commanded speed | 29.4 | 30.1 | +0.021 |
| wind, mass, motor τ, aero dev | — | — | ≤ +0.17 |

Failures are **6.1 m/s short on descent rate**: the aircraft will not go down as steeply as
commanded. A stratified sweep (γ forced, n = 24 per angle, so every angle gets equal weight)
makes it unambiguous and monotonic:

| γ | −40 | −30 | −20 | −10 | 0 | +10 | +20 | +30 | +40 |
|---|---|---|---|---|---|---|---|---|---|
| median err | 11.78 | 11.08 | 8.32 | 8.92 | 4.88 | 3.69 | 3.01 | 2.40 | **2.02** |
| % > 10 m/s | 62% | 54% | 46% | 38% | 25% | 4% | 4% | 8% | 4% |

**Descents 10.16 vs climbs 2.44 — a 4.2× gap at the same speeds.** And it is present in EVERY
band, scaling with speed:

| band | γ −45…−20 | γ +20…+45 | ratio |
|---|---|---|---|
| low 0–10 | 0.93 | 0.38 | 2.4× |
| mid 10–18 | 2.53 | 0.57 | 4.4× |
| high 18–25 | 5.65 | 1.08 | 5.2× |
| vhigh 25–34 | 10.82 | 2.29 | 4.7× |

## Hypothesis 1 — thrust floor: REFUTED as the primary cause (mine, tested, failed)
Holding a steep descent needs the throttle closed. Nominal trim thrust at γ = −40°: 121.7 N at
16 m/s but **0.1 N at 20 m/s**, ~2–6 N above that — the aircraft sits on the `T ≥ 0` boundary
with no authority to reduce thrust, one-sided control exactly like the classical cascade's
windup dilemma. Re-solving trim **per DR draw** (±20% aero, mass 13.6–14.1, 24 draws/cell):

| | γ=−40 | γ=−30 | γ=−20 | γ=0 |
|---|---|---|---|---|
| infeasible (no balance exists) | 0–4% | 0% | 0–4% | 0% |
| **throttle at floor (T < 1 N)** | **17–42%** | 0–4% | 0% | 0% |

Real but **not the explanation**: the floor is hit only at γ ≤ −30, which predicts a cliff
between −30 and −20. The measured profile is a smooth monotonic ramp from +40 to −40, and it
cannot explain why level flight (4.88) is more than twice as hard as a +40° climb (2.02) when
both have 90–137 N of thrust margin. Also note infeasibility is ~0% everywhere: **failures are
not physically impossible states.**

## Hypothesis 2 — required TRIM TILT: **REFUTED by my own table** (kept as a worked error)
What varies smoothly with γ is the attitude the command implies. At 28 m/s the trim tilt runs
28.9° (γ=+40) → 53.4° (level) → 88.9° (γ=−40), and above 32 m/s a steep descent needs 93–105°,
i.e. body-z below the horizon. Correlating median error against required trim tilt across all
20 (band × angle) cells:

| predictor | correlation with median error |
|---|---|
| **required trim tilt** | **+0.774** |
| commanded speed | +0.650 |
| flight-path angle γ | −0.438 |

I initially read this as a law ("error doubles every ~16° of tilt") and it is **wrong**. The
refutation is inside the same sorted table — matched-tilt cells:

| cell | required tilt | median err |
|---|---|---|
| mid γ=+0 | 26.9° | **0.82** |
| mid γ=−32 | 26.9° | **2.53** |
| high γ=+32 | 26.6° | **1.08** |

**Identical tilt, 3.1× different error**, and what separates them is the sign of γ. The second
pair crosses bands the wrong way for a tilt law too: high γ=+32 (26.6°, 1.08) beats mid γ=−32
(26.9°, 2.53) — the *faster* command is easier because it is a climb. Tilt cannot be the
unifying variable if error triples at fixed tilt.

Two further reasons the correlation was never evidence:
1. **+0.774 vs +0.650 proves nothing.** Tilt is a monotone function of both speed and γ, so a
   combination beating each one-variable marginal is close to guaranteed.
2. **The predictor is solver noise.** Trim tilt at V=16 runs γ=−40: 37.3°, γ=−30: **47.0°**,
   γ=−20: 43.4° — non-monotonic in γ, physically implausible, and the same underdetermined
   flat-direction wander already diagnosed in the elevator column (trial 70 physics note).
   Regressing against it was unsound.

Kept in the record rather than deleted: the failure mode is instructive. A plausible mechanism
plus a correlation that beat its marginals looked like a law, and the disproof was already
printed in my own output.

## Hypothesis 3 — INCOMPLETE TRANSITION (settling time): **REFUTED**
Every episode starts **at rest in hover**, where the thrust vector already points along a climb.
Reaching γ=−40° at 30 m/s means pitching past horizontal and building ~19 m/s of sink from a
standing start, with only 5 s elapsed before the 3 s scoring window opens. The failure signature
fits being *behind* the maneuver rather than unable to hold it: descents are simultaneously
**under-descending (+6.1 m/s)** and **under-speed (deficit +2.3 to +5.3 m/s)** — an aircraft
fighting a controllability limit would overshoot one of those, not undershoot both.

Discriminator: repeat the γ sweep at `--ep-len 20` (2.5× longer, matching trial 21's protocol).

| protocol | descents | climbs | ratio |
|---|---|---|---|
| 8 s | 10.16 | 2.44 | 4.2× |
| **20 s** | **11.04** | **2.28** | **4.8×** |

**More time does not help — the gap is slightly wider.** Steep descents end 20 s episodes still
7–11 m/s short on sink rate. The policy is not behind the maneuver; it settles into a
persistently wrong state. Settling time refuted, and with it my reading of the
"under-descending AND under-speed" signature.

## Hypothesis 4 — ENTRY vs STABILIZATION: it is **STABILIZATION** (the decisive test)
Applying the trial-27 discriminator to direction: start episodes AT the commanded velocity in
near-trim attitude (`trim_init_frac=1.0`) and see whether the policy can HOLD what it cannot
reach. Verified genuine: median |v₀ − target| at t=0 is 1.54 m/s.

| γ bin | n | median err | % > 10 | vertical err |
|---|---|---|---|---|
| −45…−25 | 30 | **12.46** | 63% | +3.31 |
| −25…−10 | 35 | 9.26 | 46% | +6.50 |
| −10…+10 | 47 | 5.41 | 15% | +2.82 |
| +10…+25 | 27 | 3.16 | 7% | +1.31 |
| +25…+45 | 37 | **1.55** | 0% | −0.12 |

**descents 12.82 vs climbs 1.88 = 6.83×, WORSE than the 4.2× from rest.** Placed in a descent
that is feasible (residual 0.000), trimmable under DR (infeasible ~0%), and worth ~1 reward/step
more than what it does instead, the policy **departs from the state** — starting 1.54 m/s away
and ending 12.5 m/s away. This is a stabilization/competence failure, not entry, not settling,
not physics, not incentive.

### A candidate origin — untested, and it implicates the campaign's own breakthrough
The policy does not merely track descents badly; it **actively leaves** them, drifting toward
shallower flight (vertical error +3.3 to +6.5 m/s). That is the signature of a learned prior
against descending — and this project spent its early trials installing exactly that. Trial 01–03
were dominated by a **dive attractor** (81.7 m/s error, "policy dives, tracks yaw only", 0/60
recoveries). The trial-04 yaw gate — THE breakthrough, 41.3 → 9.2 — worked precisely by making
diving unprofitable, and every acceptance test since has scored "descending fast" as the failure
state to recover FROM.

The hypothesis: **the fix that destroyed the dive attractor also taught a general aversion to
commanded descent, which now caps the fast bands.** Consistent with all the evidence here (a
learned bias explains departure-from-feasible-state, direction-sign dependence at constant tilt,
and severity growing with how much sink the command requires) but **not tested** — separating it
from "descents are simply harder to stabilize" needs a training run with descent-weighted
targets or a gate ablation, which the no-training directive excludes. Flagging it because if it
is right, the fast-band gap is a curriculum artifact, not an aerodynamic limit.

## Does the reward fix touch the descent problem? Test attempted, INCONCLUSIVE
Ran the same γ sweep on trial 73's promoted `basin` arm — a genuine single 0–45 policy with
`rel_basin=1.0` (n=20/angle, band 25–45):

| γ | −40 | −30 | −20 | −10 | 0 | +10 | +20 | +30 | +40 |
|---|---|---|---|---|---|---|---|---|---|
| median err | 27.88 | 21.21 | 18.08 | 14.78 | 15.81 | 13.18 | 13.59 | 14.13 | 15.29 |
| vertical err | +26.12 | +21.68 | +16.15 | +11.70 | +6.60 | +0.87 | −3.46 | −6.35 | −10.68 |

Descents 20.57 vs climbs 14.18 = **1.45×**, far below the specialists' 4.2×. **This does not
show the reward fix cures the asymmetry** — the arm is a 4M-step screen scoring 0% below 1 m/s in
every band, so its error is dominated by general incompetence and the ratio is compressed by a
floor effect. Comparing it to 36M-step specialists confounds mechanism with training budget.

What the vertical column does show, and it is suggestive: the policy undershoots commanded
vertical velocity in **both** directions (+26.1 descending, −10.7 climbing) — it flies too level
overall, with the bias much larger downward. A converged basin policy would be needed to separate
"the reward fix fixes descents" from "everything is equally bad at 4M steps", and that requires
training.

## What survives regardless
The descent/climb asymmetry at **matched speed**, from the stratified sweep alone — no trim
table, no tilt regression, no solver output involved: nine angles, n=24 each, monotonic,
10.16 vs 2.44, replicated across all four bands. Uniform-on-the-sphere target sampling means
**half of all commands are descents**, so whatever its cause, this asymmetry has been setting
the band medians for the whole campaign and nobody had looked.

## Summary of the mechanism hunt
| hypothesis | test | verdict |
|---|---|---|
| Reward dead at speed (trial 70) | reward at each policy's own operating point | **refuted there** — unclaimed reward is largest at vhigh and the reward is convex; trial 70 applies to the far-field approach only |
| Physics / infeasible commands | per-DR-draw trim solve | **refuted** — infeasible ~0% everywhere |
| Thrust floor at descent | per-draw throttle-at-floor rate | **refuted as primary** — bites only at γ≤−30, but the penalty ramp is smooth and γ=−20 has full margin |
| Required trim tilt | within-policy (low band, tilt constant 2.4–3.9°) | **refuted** — 2.08× error spread at constant tilt |
| Settling time from hover start | 20 s vs 8 s episodes | **refuted** — gap slightly wider at 20 s |
| **Entry vs stabilization** | trim-start hold test | **STABILIZATION** — 6.83× gap when placed in the state |

The phenomenon is solid and replicated; five candidate causes are eliminated; the surviving
description is that the policy cannot (or will not) hold a commanded descent.

## Honest limits
- **Four of five mechanisms I proposed were refuted, two by data I had already printed.** What is
  established is the phenomenon and the entry/stabilization split — not a cause.
- Stratified sweeps (n=24/angle, 9 angles, 4 bands) are the numbers to trust; the earlier
  cross-band bins (n=11–17) were noisy and produced the spurious tilt correlation.
- Matched-tilt pairs mostly compare **different policies** across bands, confounding tilt with
  policy identity — which is why the within-policy low-band test is the one that settles it.
- The stratified sweep overrides `target_vel` after `reset()`, so the first action of each
  episode sees the reset's target. Scoring uses the last 3 s, so this is immaterial, but it is a
  deviation from the standard eval path.
- **No causal test was run and none can be** under the no-training directive: confirming any
  mechanism would need training with a modified target distribution.

## What this would imply for the goal (contingent on the 20 s result)
If the penalty proves to be settling time, the 0–50 m/s goal is closer than the band medians
suggest — the numbers would be understating steady-state capability because 8 s is not enough to
establish a fast descent from hover, and the fix is a protocol/spec choice, not training.

If it proves to be a real control asymmetry, then a spec question is worth putting to the user:
**is a −40° descent at 30+ m/s an operationally required command, or an artifact of sampling
target directions uniformly on the sphere?** Half of all commanded targets are descents purely
because of that sampling choice, and nothing in the requirement ("set velocity error <1 m/s on
any physically-possible target") was ever stated to weight them that way.
