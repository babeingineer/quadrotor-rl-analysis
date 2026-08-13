# Trial 83 — xw83: the RATE interface under the modern recipe (TIE) — and the tilt cap is REFUTED

**STATUS: COMPLETE.** 64M steps, one lineage, finished 2026-08-11 22:39. Curriculum
0-18 → 25 → 34 → 45 → 50 then three convergence stages at 0–50. **One variable vs xw80_h:
`att_cmd` off.**

## Why
User: *"why is it hard to use rate-controller? … i want to use rate-controller"* then *"can you
make single policy rate controller based to win the current one?"*

Trial 82 found the campaign's belief that `att_cmd` was essential rested on a confound: the
attitude interface was adopted at trial 32 against a **pre-reward-fix** mid-band baseline, and
**every** CTBR result predates `rel_basin` (73), `rel_obs` (79) and the curriculum (80) — all
interface-independent. Meanwhile the most precise policy in the project, xw48c (0.44 median /
**0.27 hover**), *is* CTBR. So the interface had never been tested fairly.

## Result — a genuine tie on velocity
Matched envelope by envelope against the attitude lineage (curriculum stages scored on their own
envelope; 0–50 stages comparable):

| stage | envelope | **RATE** | **ATTITUDE** |
|---|---|---|---|
| a | 0–18 | 2.80 / 6% | 2.70 / 3% |
| b | 0–25 | **1.75** [1.54–2.05] / 27% | 1.77 / 26% |
| c | 0–34 | 2.92 / 19% | **2.78** / 23% |
| d | 0–45 | **3.45** / 17% | 3.57 / 23% |
| e | 0–50 | **3.45** [2.59–4.61] / 22% | 3.85 / 21% |
| f | 0–50 conv | 3.23 | **3.07** |
| g | 0–50 conv | **3.11** | 3.22 |
| h | 0–50 conv | 3.16 [2.36–4.18] / 22% | **2.97** [2.54–3.77] / 25% |

**Every comparison sits inside overlapping CIs, with each interface winning about half the
stages.** The interface is not what was holding this task back — the reward and observation
scaling were. Trial 32's apparent attitude win was an artifact of its baseline.

**Attitude still wins the secondary axes**, so the deliverable does not change:

| metric | RATE (xw83_h) | ATTITUDE (xw80_h) |
|---|---|---|
| pooled median | 3.16 | **2.97** |
| %<1 | 22% | **25%** |
| pooled yaw | ~27° | **21.7°** |
| descents (25–45) | 14.64 | **9.55** |

Yaw was rate's clearest weakness and it converged rather than collapsing: 39.8° → 26.1° → 27.9°
→ 27.1° across the curriculum, versus attitude's 12.3° → 17.1° → 20.4°. Plausible reason: under
`att_cmd` the inner P-loop owns roll/pitch, so the policy's yaw channel is comparatively clean,
while CTBR makes one memoryless net coordinate all three axes.

## ★ The real payoff: the 80° TILT CAP IS REFUTED as the descent cause
The `att_cmd` decode confines the commanded thrust axis to the upper hemisphere with tilt capped
at **80.0°**, while steep descents at 35–50 m/s need a measured **93–105°**. Trials 78 and 81
both tried to lift that cap and both failed for implementation reasons (78 destroyed action
resolution; 81 could not warm-start across the semantics change), leaving the hypothesis
untested. **CTBR has no attitude parameterisation and therefore no cap at all** — so this run
tests it for free:

| policy | tilt cap | descents | climbs | ratio |
|---|---|---|---|---|
| xw80_h (attitude) | **80°** | 9.55 | 2.87 | 3.3× |
| **xw83_h (rate)** | **none** | 14.64 | 4.07 | **3.6×** |

**Same asymmetry, and worse in absolute terms, with the cap entirely removed.** The action-space
tilt limit was never the cause of the descent problem. Stable across xw83's three convergence
stages (3.0×, 2.4×, 3.6×).

This is the **sixth** eliminated explanation for the descent asymmetry, after physics
(per-draw trims feasible ~0% infeasible), the thrust floor (bites only at γ≤−30), trim-tilt
correlation (2.08× spread at constant tilt), settling time (20 s gap *wider*), and entry (it is
stabilization, 6.83× when started in the descent). The phenomenon is robust and its cause is
still unknown — but the interface is now definitively off the list.

## Verdict
- **Rate control is viable and competitive**: statistically tied on velocity at every stage, at
  equal budget, under the modern recipe. If a simpler stack matters, it is a reasonable choice
  and it owns the low band outright (xw48c).
- **It does not win**, so `results_velyaw_xw80_h` remains the deliverable on %<1, yaw, and
  descents.
- **The tilt-cap line of attack is closed.** No further interface surgery is justified.

## Honest limits
- Single seed per arm; a ~6% pooled-median difference is well inside that noise. The correct
  reading is "indistinguishable", not "attitude is 6% better".
- Rate ran with the **stiff** rate PID (25,25,15 / 6,6,3) that was tuned for `att_cmd`, chosen to
  isolate the interface. xw48c's softer defaults (6,6,4) were not tried at 0–50; the tie means
  the pre-registered soft-gain retest is no longer needed to avoid a false refutation, but rate
  might do slightly better with its own gains.
- Yaw comparisons are pooled across bands. The spec only requires yaw at hover/low, so the
  per-band hover figure is the one that should gate any decision.
