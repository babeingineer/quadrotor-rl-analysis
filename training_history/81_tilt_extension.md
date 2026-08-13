# Trial 81 — resolution-preserving tilt extension: FAILED (warm-start confound)

**STATUS: COMPLETE.** 3 stages, 22M steps, warm-started from `results_velyaw_xw80_h` at 45.83M.
Finished 2026-08-10 13:17. **Verdict: FAILURE — regressed in every band and did not fix descents.**

## Why it was run
xw80_h (trial 80) is the deliverable: single 0–50 policy, pooled 2.97, 25% <1. Its one unfixed
weakness is descents — **9.55 vs 2.87 for climbs (3.3×)**, with a +15.9 m/s vertical undershoot
at γ=−40. Steep descents at 35–50 m/s need **93–105°** of trim tilt while `att_cmd` caps
commanded tilt at **80.0°**. Trial 78 tried to lift that cap by rescaling `|xy|` linearly onto
0–120° and was 3.5× worse (it halved resolution everywhere). This attempt preserves resolution.

## What (one variable vs xw80_h)
`--att-tilt-ext 120`: legacy `arcsin` mapping kept **bit-for-bit** for `|xy| ≤ 0.9` (0–64°), with
only the outer 10% of the action ball spanning 64° → 120°. Verified before launch:

| \|xy\| | 0 | 0.3 | 0.6 | 0.9 | 0.95 | 1.0 |
|---|---|---|---|---|---|---|
| legacy | 0 | 17 | 37 | 64 | 72 | **80 (cap)** |
| ext=120 | 0 | 17 | 37 | 64 | **92** | **120** |

## Result — worse everywhere, and descents unchanged
| stage | steps | pooled median (0–50) | %<1 |
|---|---|---|---|
| xw80_h baseline | 45.8M | **2.97** [2.54–3.77] | **25%** |
| a | +6M (resumed) | 7.53 [5.75–12.76] | 16% |
| b | +8M | 5.72 [4.89–6.61] | 14% |
| c | +8M | 5.26 [3.67–6.20] | 17% |

Partial recovery (7.53 → 5.72 → 5.26) but never back to baseline after 22M steps. Per band at
stage c, **every band is worse**: hover 0.82 (vs 0.41), low 0.81 (0.56), mid 2.64 (1.25), high
2.92 (2.28), vhigh 7.53 (5.58), top 11.30 (9.79). Yaw also degraded (10–67° vs 2–39°).

**The hypothesis under test — descents:**

| policy | descents | climbs | ratio |
|---|---|---|---|
| xw80_h | 9.55 | 2.87 | 3.3× |
| **xw81_c** | 18.36 | 5.88 | **3.1×** |

**Unchanged.** Both halves got worse together; the extension bought no descent-specific benefit.
Also flat across steepness (steep −40/−30 = 17.60 vs shallow −20/−10 = 19.78), so the reach past
90° was not the missing ingredient.

## Why it failed: the warm-start broke the action mapping
Stage a's γ sweep is diagnostic — vertical error went **large and NEGATIVE at climbs**: −28.5 m/s
at γ=0, −36.2 m/s at γ=+40. Told to fly level, the aircraft sank at 28 m/s. The reason is direct:
`|xy| = 0.95` used to command **72°** of tilt and now commands **92°**. The policy issues commands
in that region roughly a third of the time, so every one of them became a large over-tilt — lift
lost, aircraft falling. It spent 22M steps re-learning a mapping it already knew, and still
finished behind.

This is exactly the pre-registered FAILURE branch: *"warm-starting across an action-semantics
change does not work; a fresh run would be required to test the mapping fairly."*

## What this does and does not establish
- **Established:** you cannot change action semantics mid-lineage and warm-start. The cost far
  exceeds any reach benefit, even when 90% of the action ball is left bit-identical. Two interface
  attacks (78, 81) have now failed for *implementation* reasons rather than for the hypothesis.
- **NOT established:** whether the 80° tilt cap actually limits the fast bands. The ratio being
  unchanged at 3.1× is weak evidence against it — but from a policy that never regained baseline
  competence, so it cannot carry much weight. **A fair test needs a fresh lineage trained with the
  extension from step zero**, at ~64M steps to match xw80. That was not run.

## Process note
I stopped this run mid-stage-a by misreading a conditional instruction ("if current training
finished…") as an order to stop. A paired checkpoint existed at 47,834,376 steps, so only ~15k
steps were lost and the run resumed from that exact pair. The periodic model+VecNormalize pairing
from trial 72 is what made recovery clean.

## Standing conclusion
**xw80_h remains the deliverable** (pooled 2.97 / 25% <1; on 0–34 it matches the four-specialist
composite at 1.51 [1.28–1.63] vs 1.22 [1.04–1.60] and additionally flies 35–50). xw81 is
superseded and its checkpoints should not be used.
