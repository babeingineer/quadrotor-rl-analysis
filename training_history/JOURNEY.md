# The journey: 81.7 → 0.44 m/s (velyaw task, XWing physics)

Concise record of how velocity error improved ~185× on the bands that were solved, what failed,
what worked, and why. Details per trial: [INDEX.md](INDEX.md). Benchmark: wind 0–20 m/s through
trial 10, **0–15 m/s (real spec) from trial 11**; from trial 59 the headline is the **composite**
(band specialists routed by commanded speed) under full DR.

**FINAL STATE (2026-08-05, campaign stopped by user directive — no new training).**

| band | median | %<1 | recovery from upset |
|---|---|---|---|
| hover 0–1 | 0.27 | 80% | — |
| low 1–10 | **0.44** | 75% | 60% |
| mid 10–18 | **0.77** | 64% | 57% |
| high 18–25 | 1.77 | 27% | 35% |
| vhigh 25–34 | 5.73 | 3% | 32% |
| pooled | 1.22 [CI 1.04–1.60] | 44% | 46% [40–53] |

**Goal met on 0–18 m/s; missed above it; 34–50 m/s never covered by any policy.** The target
moved 0–25 → 0–45 → 0–50 m/s over the campaign. Trims are verified feasible within actuator
limits to 60 m/s, so what remains is controller quality, not physics. The likely reason the fast
bands never trained is documented at trial 70 (a reward that goes numerically dead at speed) —
found by reading the reward, quantified, implemented, and **never trained**.

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

**NOT TRAINED** — user directive to stop starting runs. So this is a quantified mechanism and a
working implementation, not a result. Lesson worth keeping regardless: *before blaming capacity,
memory, or interference for a wide-range RL failure, evaluate the reward numerically at the
edges of the range.* Six trials tested architecture; none had checked whether the objective was
still finite out there.
