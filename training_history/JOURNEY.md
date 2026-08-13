# The journey: 81.7 m/s → one policy over 0–50 m/s (velyaw task, XWing physics)

Concise record of how velocity error improved ~185× on the bands that were solved, what failed,
what worked, and why. Details per trial: [INDEX.md](INDEX.md). Benchmark: wind 0–20 m/s through
trial 10, **0–15 m/s (real spec) from trial 11**. The headline system was the **composite** (band
specialists routed by commanded speed) from trial 59, and is the **single 0–50 policy** from
trial 80 onward. All numbers under full DR.

**CURRENT STATE (2026-08-14, campaign ACTIVE — autonomy restored 08-13).**

The deliverable is a **SINGLE policy over 0–50 m/s**, currently **`results_velyaw_xw87_c`**
(xw80_h + 16 s episodes): pooled **2.62 [2.06–3.32] / 25% <1** @8 s protocol — hover 0.35 (83%),
low 0.46 (81%), mid 1.37, high 1.84, vhigh 4.63, top 7.09. It supersedes xw80_h (2.97), whose
numbers below stand as the 8 s-era reference. In flight: xw88 (more 16 s stages) and xw86
(seed-2 convergence).

| band | single policy | composite specialist |
|---|---|---|
| hover 0–1 | **0.41 (83% <1)** | 0.27 |
| low 1–10 | **0.56 (81% <1)** | 0.44 |
| mid 10–18 | 1.25 (36%) | 0.77 |
| high 18–25 | 2.28 (15%) | 1.77 |
| vhigh 25–35 | 5.58 (1%) | 5.73 ← single policy wins |
| top 35–45 | 9.79 (1%) | **none exists** |
| pooled 0–50 | **2.97 [2.54–3.77], 25% <1** | cannot fly the range |

On the composite's own 0–34 range: **1.51 [1.28–1.63] vs 1.22 [1.04–1.60]** — CIs overlap. One
network essentially matches four specialists plus a router, covers a band none of them can fly,
and costs less in total.

**The <1 m/s goal is not met.** Hover and low clear it by median; mid/high/vhigh/top do not.

## ★ 2026-08-07..10 — how one policy caught four specialists
Three ingredients, each isolated:
1. **Scale-invariant approach reward** (73): absolute reward widths are numerically dead far from
   a fast target (shaped gradient 1.3e-1 at 5 m/s → **3.9e-22 at 50**). Basin width tracks the
   commanded speed; goal terms stay absolute.
2. **Command-scaled observation** (79): `vel_err / MAX_SPEED` leaves a 0.5 m/s hover error at
   0.01, and VecNormalize's running std is dominated by fast-band errors. Adding
   `vel_err / max(|target|, 8)` took hover **2.01 → 0.74, 0% → 67% <1** — pooled-neutral, so the
   aggregate hid it. Second time in this campaign a real effect was masked by a pooled statistic.
3. **Speed curriculum in one lineage** (80): 0-18 → 0-25 → 0-34 → 0-45 → 0-50, then convergence.
   Flat 0–50 plateaued at 4.04 / 3% <1; the curriculum reached **2.97 / 25% <1**.

Refuted along the way: **full-sphere attitude** (78) was 3.5× worse — lifting the 80° tilt cap by
rescaling the action map halved resolution everywhere, worst at hover (3.7×). The lesson is that
`arcsin` was well matched to the task (fine near hover, coarse near the cap), and any interface
change must preserve that.

**What is left.** The fast bands, and specifically **descents**: 9.55 vs 2.87 for climbs (3.3×),
+15.9 m/s undershoot at γ=−40. Steep descents at 35–50 m/s need 93–105° of tilt against an 80°
cap.

**Trial 81 tried to lift that cap and FAILED — for a reason worth remembering.** The mapping
change was carefully resolution-preserving (legacy `arcsin` kept bit-for-bit below |xy|=0.9), but
it was **warm-started** from xw80_h, and above 0.9 the same action now meant something else:
|xy|=0.95 went from commanding 72° of tilt to 92°. The policy issues commands in that region
about a third of the time, so a third of its behaviour instantly became a large over-tilt — told
to fly level, the aircraft sank at 28 m/s. Twenty-two million steps of re-adaptation got it from
7.53 to 5.26, still far behind the 2.97 it started from, and **the descent/climb ratio was
unchanged (3.1× vs 3.3×)**.

Two interface attacks (78, 81) have now failed for *implementation* reasons rather than the
hypothesis. **The tilt-cap question is still open**, and a fair test needs a fresh ~64M lineage
with the extension from step zero — not a continuation. General lesson: **action semantics are
not a continuation-safe knob**, unlike reward weights or the training distribution.

## The scoreboard

| trial | change | vel err | verdict |
|---|---|---|---|
| 01 xwaero | XWing aero + airframe, motors only | **81.7** | ✗ policy dives, tracks yaw only |
| 02 xw6 | + elevons (6 actions), 110 N motors | **41.3** | ~ actuation fixed, dive attractor stays |
| 03 xw7 | + tough-init 30% + wind curriculum | **39.7** | ✗ 0/60 recoveries — exposure alone useless |
| 04 xw8 | **+ yaw gate** (yaw pays only if velocity tracked) | **9.2** | ✓✓ breakthrough — dive optimum destroyed |
| 05 xw8b | + 6M steps | **7.36** | ✓ yaw self-recovered 20.8°→13.7° |
| 06 xw10 | ablation: gate WITHOUT tough-init/curriculum | **7.89** | ✓ gate alone is the active ingredient |
| 07 xw11 | + narrow precision reward peak | **7.53** | ~ helps low band only |
| 08 xw12 | **+ attitude gate** (release yaw in wing-borne flight) | **6.82** | ✓ high band 13.3→10.9 |
| 09 xw13 | fresh run, full stack | **6.70** | ✓ yaw 4.1° (solved); velocity floor appears |
| 11 xw15 | **real spec** (wind 0–15) + 512×512 net | **5.55** | ~ capacity ruled out (512=256) |
| 12 xw16 | coverage width 12.5→5 (kill loitering subsidy) | **5.44** | ~ small gain, reward rungs exhausted |
| 13 xw17 | **γ 0.997 + 14 s episodes** (transition economics) | **5.26** | ~ best; high band 8.58; yaw collapsed 55° |

Crash rate: 0% from trial 01 onward. Yaw error at best: 4.1° (xw13).

## What FAILED (and the lesson)

| tried | result | lesson |
|---|---|---|
| Tough-init exposure alone (03) | 0/60 recoveries after 2.4M dive-start steps | exposure can't beat a reward barrier |
| Wind curriculum (03) | no effect | staging doesn't fix incentives |
| More steps past plateau (05, 12) | flat or worse | saturation is real; keep best checkpoint |
| Bigger net 512×512 (11) | = 256×256 | capacity was never the limit |
| Fresh vs stacked continuations (09) | same floor | lineage baggage wasn't the limit |
| Training at real wind spec (11) | ≈ eval-only gain | robustness training wasn't the waste |
| Reward sharpening beyond #12 | ~0.2/iteration, plateaus | shaping is exhausted at ~5 m/s |

## What SUCCEEDED (in order of impact)

1. **Elevons (02)** — 82→41. Motor torque is constant with airspeed; aero moment grows with V².
   Only control surfaces (also V²) keep pace. Actuation must match the disturbance physics.
2. **Yaw gate (04)** — 41→9.2. THE breakthrough. A stable dive *earned +1.4/step* from the
   always-on yaw reward; every partial recovery scored worse. Gating yaw by velocity success
   flipped the equilibrium and put gradient along the recovery path.
3. **Attitude gate (08)** — released yaw in wing-borne flight, where the nose is slaved to the
   velocity vector and a random desired_yaw is physically unsatisfiable.
4. **Real wind spec 0–15 (11)** — 6.70→5.61 for free; the 0–20 default embedded corners the
   real aircraft never faces.
5. **Coverage narrowing + precision peak (07, 12)** — each bought its predicted local gain.
6. **Transition economics γ+episode length (13)** — best high band (8.58) + best dive
   recovery (57%), confirming the maneuver-investment theory, but cost yaw (fix queued).

## The one recurring failure mode (found 3×, worth remembering)
**Every plateau traced to a reward term paying comfortably inside the failure regime:**
dive + full yaw payout (04) → half-tilt + yaw payout (08) → loitering + 75% coverage payout
at 9.5 m/s error (12). Diagnosis method that worked every time: per-step reward accounting of
the observed behavior vs the desired one — if the failure pays within ~1 unit of success,
PPO will stay in it. Fix the incentive; only then does exposure/steps/capacity matter.

## Where it stands (updated after the feasibility campaign)
- Generalist track closed at **5.26** (xw17 @12M; continuation regressed).
- Specialist probe: specialization alone bought nothing at 8M (2.31 ≈ generalist 2.27)…
- …but **convergence did** (trial 16): **hover 0.78 m/s ✓**, low band 1.89 mean / **0.82
  median**, 59% of episodes < 1 — under the FULL spec. First sub-1 numbers of the project.
- The residual is now precisely located: the **strong-wind tail** (draws ≳10 m/s at low speed)
  and the **mid/high bands**. The <1 m/s question is a spec/target decision plus a per-band
  engineering campaign (regime split), not a training mystery.

## The feasibility campaign (trials 18–25): "can <1 m/s be done at all?"
Provoked by the user's premise "if a human can fly it, RL can learn it." Findings, in order:

1. **Classical ceiling probes (21)**: a 60-line cascade + elevator assist under FULL spec:
   low **0.65 median @20 s**, mid **0.20 median (60% <1)**, high 3.90 median (26% <1).
   The premise holds — simple control matches RL where it's stable; settle time and a TRUE
   integrator (leak τ=3 bounds steady error ~3×) were the two exported insights.
2. **Identification refuted (20)**: aero-DR-OFF ablation at high band was WORSE (11.40 vs
   8.94) — the ±20% aero uncertainty is not the bottleneck; DR even regularizes.
3. **High-band residual diagnosed (21 add. 4–5)**: not oscillation — a CONSTANT offset from
   integrator saturation, trapped in an authority/windup dilemma structural to fixed-gain
   cascades (clamp 8→8.4, 80→38.4; anti-windup fails too). RL doesn't share the dilemma.
4. **PHYSICS CLEARED (21 add. 5–6)**: fine trim optimization proves exact force balances
   exist for **100% of draws** — including the worst corner (25 m/s target + 15 m/s adverse
   wind = Va 40, heaviest mass, ±20% extremes; all residuals 0.000 m/s²). At trim, drag is
   tens of N vs 440 N thrust (small-alpha insight — the user's). **<1 m/s has no physics
   obstruction anywhere in the envelope; the entire gap is controller robustness.**
5. **Recipe-bundling failure (22)**: importing the classical insights AS A 4-VARIABLE BUNDLE
   (γ 0.999 + 20 s + true integrator + stiff gains) regressed the low band 0.82→2.08 median
   with the known γ≈1 yaw collapse (53°). Lesson re-learned: one variable per trial.
6. In flight: **xw23** (mid, recipe @ γ 0.997), **xw24** (high, same — the first fair RL
   test on a band with proven 100% feasibility), **xw25** (low isolation: xw18b + true
   integrator + 20 s only), **lstm3** (full-envelope RecurrentPPO vs xw17's 5.26).

## Where it stands (updated 2026-07-31)
- Best per band: hover **0.78 ✓** | low **0.82 median** (xw18b; 59% <1) | mid RL untested
  fairly (classical proves 0.20 median possible) | high RL 8.94 (classical median 3.90).
- Physics is proven not to be the limiter anywhere. The <1 m/s campaign is now pure
  robustness engineering: per-band recipes, then merge (per-band policies or distillation).

## ★ 2026-08-02 — first sub-1 band
Mid band (10–18 m/s) robust median **0.92 [0.85–1.04], 53% <1** under the full spec
(wind 0–15, ±20% DR), at 36M steps. The recipe that did it, in causal order: trim-init
(goal-state exposure) + attitude-setpoint interface (structural stabilization of the
unstable wing-borne trim) + robust-CI-gated budget ladder. Now transferring to the high
band (trial 37), then the 25–45 m/s extension.

## Range-width lesson (trials 62/63, 2026-08-05)
At high dynamic pressure the training SPAN matters as much as the recipe:
- 25-34 trained on 21-34 (scaffold below the band): **3.77 median**
- the same lineage narrowed to 25-34: 5.06
- a lineage stretched to 27-40 then narrowed: 5.30
Coverage and precision trade off inside one network, and an all-hard target distribution
removes the easy-win gradient that keeps a policy competent. Practical rule adopted, then CORRECTED (trial 65): re-running 18-25 with scaffold below it
(train 14-25) gave 2.48 vs the champion's 2.03 - the rule did not transfer. The 25-34
champion's edge came from its LINEAGE (it climbed through slower speeds over many stages),
not from the instantaneous target distribution. Lesson (confirmed by trial 66, which reproduced the degradation at 25-34 too): **how a
fast-band policy was grown matters more than any span it is currently sampling — and
further training at the fast bands, at every span tried, makes them worse.** The fast-band
champions are checkpoints to preserve, not lineages to continue.

## ★ 2026-08-05 — the safety column nobody was watching, and a fix with no retraining
Acceptance testing found every band champion recovers from upsets far worse than the old
full-envelope generalist. The campaign had optimised *nominal precision* for 60+ trials and
never gated on recovery, so the regression accumulated invisibly.

**Cause: state coverage, not curriculum.** The generalist has `tough_init=0.0` — it never
trained on failure states at all. Its robustness is breadth of experience alone. Confirming
this from the other side, reintroducing failure-state training on the mid champion moved
recovery 12% → 22% but walked precision 0.82 → 0.89 → 0.97, straight onto the 1 m/s goal
line. Dose works at a bad exchange rate. (Earlier note "dose refuted" was premature — filed
after one rung of a two-rung ladder; corrected in trial 69.)

**Fix: route, don't retrain.** A supervisory switch hands control to the generalist while the
aircraft is upset and back to the champion once settled — a routing rule over two trained
networks, so the pure-RL constraint holds. Final: pooled recovery **22% [17–28] → 46% [40–53]**,
median post-upset error 38.8 → 9.8 m/s, engaging on **4%** of nominal flights.

**Reporting lesson (advisor caught this).** I first called the precision cost "unchanged to two
decimals", which was true of the median and *guaranteed* to be — at a 4% engagement rate a
median over 400 episodes cannot move. p90 can, and did (in both directions, depending on whether
the seeds were the ones the detector was calibrated on: this is why selection is now out of
sample). The statistic that actually answers the question is a **paired** one: join armed and
disarmed runs on (band, seed), which the deterministic harness permits — 379 of 400 episodes
come out byte-identical, and on the 16 real engagements mean error goes 21.18 → 15.36, helping 9
and hurting 7 with improvements outweighing regressions 7.4:1. **Net beneficial with real
per-episode variance** — not "no cost". Never report a rare-event effect through a median.

Two methodological lessons, both from my own errors:
1. **A detector tuned on one band is not a detector.** Hand-set thresholds looked fine on the
   mid band (18% spurious) and fired on **47%** of nominal flights across the roster. A
   tailsitter's cruise is near-horizontal (nominal tilt p95 reaches 110°), so an absolute tilt
   limit flags ordinary fast flight; and these policies routinely exceed a 2.5 rad/s rate
   limit. Comparing tilt to the **trim attitude the command implies**, plus dwell, cut
   spurious firing 16× to 3%. Calibrate against recorded nominal AND failure data, per band.
2. **Sharing one env between two policies leaks state.** `apply_cfg()` mutated `MAX_SPEED`
   for obs scaling, but the env samples the *command* from that same attribute at reset — so
   each episode inherited the previous episode's policy scaling, silently commanding the mid
   champion up to 25 m/s in an 18 m/s test. Fixed by resetting the band range explicitly.

**Arming is envelope-gated**: the generalist trained to 25 m/s, and arming it above that made
recovery *worse* (28% → 5% on the 25–34 band). The same state-coverage principle in reverse —
a policy is robust inside its envelope and unreliable outside it.

## ★ 2026-08-05 (late) — why ONE policy never worked: the reward was numerically dead at speed
Asked to find a way to train a single policy over 0–50 m/s, I read the reward instead of
proposing another architecture. All three velocity terms have **absolute** widths (2 m/s,
5 m/s coverage, 0.5 m/s precision peak). An episode starts at rest, so commanded V means
initial error d = V, and the shaped reward there is:

| V | 5 | 18 | 25 | 34 | 50 |
|---|---|---|---|---|---|
| shaped gradient at rest | 1.3e-1 | 1.1e-3 | 3.7e-6 | 1.2e-10 | **3.9e-22** |

**21 orders of magnitude.** Beyond ~14 m/s of error the only surviving signal is a linear ramp
with no shape — and its coefficient is `0.4/MAX_SPEED`, so a 0–50 policy gets a **5× weaker**
far-field pull than a 0–10 specialist (0.0080 vs 0.0400) while the control-effort penalties it
competes with (≈2e-3) do not shrink. **Asking for a wider envelope mechanically weakens the one
term that still functions there.**

This retro-explains most of the campaign's shape, which is why it is worth recording even
untested:
- **trim-init was the biggest gain at speed** (27) because it starts episodes *inside* the only
  region where shaped reward exists — a workaround for a dead reward, not a curriculum insight.
- **fresh fast-band training is a dead end** (54); **further fast-band training always hurt**
  (62–66) because the dominant remaining gradient is the smoothness penalty → do less → the
  "loitering equilibrium" of trials 11–12.
- **precision WEIGHT changed nothing** (31, 0.7→1.5): scaling a 1e-22 term leaves it 1e-22.
- **banding worked partly by accident** — cutting MAX_SPEED restored the reward slope.

Fix implemented (`rel_approach`): approach terms become scale-invariant (basin width and linear
pull ∝ commanded speed, reproducing exactly what a specialist at that speed felt), while every
**goal** term stays absolute — a relative goal would pay full reward for ±25 m/s at 50 m/s.
Far-field gradient improves 2.4–5.9× with near-field shape unchanged; legacy is bit-identical at
`rel_approach=0`.

**Superseded by trial 73, which actually ran the ablation**: four matched 4M arms (legacy /
command-linear / basin / both) on one 0–45 policy. `basin` was PROMOTED — worst-band median
18.93 vs legacy's 32.48, top band −41.7% — confirming the mechanism is real. But **all four arms
scored 0% of episodes below 1 m/s**, so the reward fix moves the fast bands without coming near
the goal, which is exactly what trial 75 then explains. Lesson worth keeping: *before blaming
capacity, memory, or interference for a wide-range RL failure, evaluate the reward numerically at
the edges of the range.* Six trials tested architecture; none had checked whether the objective
was still finite out there.

## ★ 2026-08-05 (audit) — best checkpoints were not propagated reproducibly

A full-history audit found an independent confound in the high-speed staircase. Physical
evaluation loads each run's best PPO weights but pairs them with the run's final
`VecNormalize` statistics. Continuation instead defaults to final PPO weights plus final stats,
and every inspected staircase script used that default. In xw55a/xw58b/xw60a the final mean
eval return was only 56%/45%/52% of the within-run best. The record therefore proves that
continuing the propagated **final** checkpoints regressed; it does not prove that continuation
from an atomic best-weight + matching-normalization checkpoint also fails.

The same audit corrected trial 70's premise: training starts are randomized up to `MAX_SPEED`,
not at rest. A million-sample calculation under the actual 0–45 reset distribution still finds
the combined fix improves median reset-gradient magnitude by 2.6–5.0× across bands, but most of
the low/mid gain comes from the command-keyed linear pull while the relative basin is inactive.
The two changes must be split and ablated after checkpoint integrity is repaired. Full evidence
and the pre-registered experiment are in [71_checkpoint_reward_audit.md](71_checkpoint_reward_audit.md).

## ★ 2026-08-05 (integrity fix) — the range staircase trained one stage behind

Implementing the checkpoint audit uncovered a larger historical bug: `continue_train.py` built
the environment arguments before applying speed-range and integral overrides. Destination configs
and evaluations used the requested range, but training used the source range. Changed-range
staircases were therefore one rung behind their labels. Most importantly, trials 63/65/66 did
not train on the narrowed/widened spans they claimed, so those causal verdicts are invalid;
trial 61 received only 8M, not 16M, of actual split-integral adaptation. xw60a did eventually
train 27–40 because its consolidation used no range override. No verified stage trained 40–45.

The code now applies overrides before constructing environments; saves paired, hashed best
model + normalization bundles; requires explicit continuation sources; redirects inherited
TensorBoard state; and separates trial 70's linear and basin changes. Simulator and tiny-PPO
smokes pass. The matched four-arm 0–45 reward screen is prepared but not launched. Full details:
[72_training_integrity_fixes.md](72_training_integrity_fixes.md).

## ★ 2026-08-06 (trial 73) — relative basin passes the clean reward screen

The first integrity-correct fresh 0–45 m/s ablation trained four matched 4M-step policies and
selected every arm from 42 model/normalization pairs by held-out worst-band physical error.
Independent evaluation used 100 episodes in each of six speed bands. Legacy failed completely:
11.60/12.60/17.11/20.04/25.97/32.48 m/s band medians and 0% below 1 m/s. Command-linear improved
fast flight but narrowly missed the top-band gate and badly degraded nominal yaw. Combining both
terms also improved fast bands but regressed low speed beyond the gate.

Relative basin alone passed: 14.12/14.40/12.21/14.25/18.10/18.93 m/s medians, zero crashes,
30.3% vhigh and 41.7% top improvement, and no below-25 regression above 30%. Nominal yaw was
23.0 degrees, better than legacy. It is still nowhere near final acceptance (0.2% pooled below
1 m/s and 5% upset recovery), so this result promotes a mechanism, not a controller. Next:
replicate basin across three seeds, then address band imbalance/convergence. Full record:
[73_xw73_reward_ablation.md](73_xw73_reward_ablation.md).

## ★ 2026-08-05 (research, no training) — the fast bands fail at DESCENTS, and it is stabilization
Continuing the analysis rather than proposing another mechanism, I checked trial 70's claim
against the trained policies and found it needed correcting: at each champion's own operating
point the **unclaimed reward is largest at vhigh (2.24)** and the reward is **convex** there
(marginal payout 0.14 → 0.54 → 1.09 as error shrinks). The fast bands are declining a large,
growing payout. Trial 70's dead zone is the far-field *approach*, not the residual.

Sorting fast-band episodes by what actually differs found it immediately: **flight-path angle**.
A stratified sweep (γ forced, n=24/angle, all four bands) shows a monotonic, replicated
asymmetry at matched speed:

| band | descents | climbs | ratio |
|---|---|---|---|
| low 0–10 | 0.89 | 0.67 | 1.3× |
| mid 10–18 | 1.83 | 0.79 | 2.3× |
| high 18–25 | 4.59 | 1.51 | 3.0× |
| vhigh 25–34 | 10.16 | 2.44 | **4.2×** |

Targets are sampled uniformly on the sphere, so **half of every band's commands are descents** —
this has been setting the band medians for the whole campaign and nobody had looked.

Five candidate causes, five eliminations (four of them mine, two refuted by data already in my
own output): physics (per-draw trim infeasible ~0%), thrust floor (bites only at γ≤−30 while the
penalty ramp is smooth), required trim tilt (the low band shows a 2.08× spread at *constant*
tilt), settling time (20 s episodes leave the gap slightly WIDER), and finally entry — the
decisive one. Started AT the commanded descent in near-trim attitude, the policy still fails:
**12.82 vs 1.88 = 6.83×, worse than from rest.** It is placed in a feasible, trimmable, better-
paying state and *departs from it*.

So this is **stabilization**, not entry, settling, physics, or incentive. Untested candidate
origin worth flagging: the policy actively drifts shallower, which is the signature of a learned
aversion to descending — and trials 01–04 spent their whole effort destroying a **dive
attractor**, with the yaw gate (the campaign's single biggest win, 41.3 → 9.2) working precisely
by making diving unprofitable. If that generalised into "don't descend", the fast-band gap is a
curriculum artifact rather than an aerodynamic limit. Testing it needs training, which is
currently stopped.

Method lesson: **stratify the evaluation before theorising.** Forty trials optimised a median
that was averaging over a 4× asymmetry nobody had measured.


## ★ 2026-08-13 — the plateau breaks: episode length was the binding protocol variable
After four failed attacks on the ~3 m/s plateau (wind oversampling null, capacity behind, rate
interface tie, tilt cap refuted), the one that worked cost nothing new: **16 s episodes instead
of 8**, continuing the same lineage (xw87). Pooled 2.97 → **2.62 [2.06–3.32]** @8 s protocol,
with the gain concentrated exactly where the settling hypothesis predicted — **top 35–45 fell
9.79 → 7.09 (−28%)**, vhigh −17%, high −19%, while hover/low also improved (0.35 / 0.46).

Why it makes sense: at 45 m/s an 8 s episode is nearly all transition — the policy barely
experiences the settled regime it is being scored on. Longer episodes deliver the same exposure
trim-init delivered (trial 27), through the protocol instead of the initial state. And unlike
action semantics (trial 81), episode length is continuation-safe.

Also that day: the seed-2 reproduction (xw86) matched seed 0 at the stage-e checkpoint
(3.62/21% vs 3.85/21%) — the recipe is not a lucky draw, though the converged number is still
being reproduced. Meanwhile the infrastructure lesson was paid for again: a zombie process that
survived a failed TaskStop retrained a finished stage for two hours and its RAM footprint killed
the legitimate convergence run's spawns. Verify kills by process list, never by tool return.
