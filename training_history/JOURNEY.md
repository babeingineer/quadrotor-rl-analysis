# The journey: 81.7 → 5.26 m/s (velyaw task, XWing physics)

Concise record of how velocity error improved 15×, what failed, what worked, and why.
Details per trial: [INDEX.md](INDEX.md). Benchmark: 120 eps, level start; wind 0–20 m/s
through trial 10, **0–15 m/s (real spec) from trial 11**. Target: **< 1 m/s** (in progress).

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
