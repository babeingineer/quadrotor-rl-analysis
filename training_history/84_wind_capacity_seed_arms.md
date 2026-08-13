# Trials 84–86 — three parallel arms on the single-policy plateau (two nulls, one partial reproduction)

**STATUS: all three ended early.** xw84 and xw86 produced usable results; xw85 did not. Stopped
under the user's wind-down instruction (2026-08-12: *"if current training finished, don't run
more trainings"*), so none was relaunched. Baseline throughout: **xw80_h = 2.97 pooled / 25% <1**
on 0–50.

## Why these three
xw80 (curriculum) and xw83 (rate interface) both plateaued near 3 m/s. The remaining error is
concentrated in the fast bands (vhigh 5.58, top 9.79). Three independent attacks were launched in
parallel: a training-distribution lever (wind), a capacity lever, and — most importantly — a
reproduction, because **every claim about 2.97 rested on a single seed**.

## Trial 84 — strong-wind oversampling: NULL
`xw80_h + --wind-oversample 0.5`. Motivation was quantitatively strong: on xw80_h, wind bins run
2.20 (0–5 m/s) → 2.89 (5–10) → **4.80** (10–15), with %<1 collapsing 38% → 28% → **11%**. Most of
the residual error lives in strong wind, and a training-distribution change is continuation-safe.

| stage | median | %<1 |
|---|---|---|
| a | 2.90 [2.31–3.51] | 24% |
| b | 3.13 [2.58–3.60] | 25% |
| **baseline** | **2.97** | **25%** |

**Flat across two stages — refuted.** Oversampling the hard draws did not make them easier; the
strong-wind deficit is not an exposure problem. This mirrors trial 03's lesson (exposure cannot
beat a structural limit) in a new place. Stage c died in a spawn crash and was not restarted; two
flat stages are sufficient to call it.

## Trial 85 — capacity retest (512×512): incomplete, and far behind
Fresh lineage, `--net 512,512`, full recipe + curriculum. Rationale: trial 11 refuted capacity,
but that was a *0–25* generalist stuck at 5.5 m/s where the binding constraint was the dead
reward (trial 70); the task is now twice as wide and one net must hold 0.4 m/s hover precision
*and* 45 m/s cruise.

| stage b (0–25) | median | %<1 |
|---|---|---|
| 512×512 (xw85) | **3.51** | 11% |
| 256×256 (xw80) | **1.77** | 26% |

**2× behind at the matched point.** Wider nets can start slower, so this is not a verdict — but
it is a weak opening, and combined with trial 11 the capacity hypothesis looks unpromising.
Killed by a spawn crash at stage c; resumable from `results_velyaw_xw85_b` if ever wanted.

## Trial 86 — SEED REPRODUCTION: the recipe reproduces (partially verified)
`--seed 2`, otherwise the exact xw80 recipe and curriculum. This was the most important of the
three: the deliverable had never been reproduced.

| stage e (0–50, matched point) | median | %<1 |
|---|---|---|
| **seed 2 (xw86)** | **3.62** [2.88–4.82] | **21%** |
| seed 0 (xw80) | 3.85 | 21% |

**Essentially identical — the recipe reproduces at the stage-e point.** Same %<1 to the percent,
medians well inside each other's CIs. That materially raises confidence in the whole
curriculum + rel_basin + rel_obs recipe.

**Caveat that must not be glossed:** seed 0 reached its headline **2.97** only through three
further convergence stages (3.07 → 3.22 → 2.97). Seed 2's convergence phase died at stage f after
all three spawn retries, so **the converged 2.97 itself is still single-seed.** What is
reproduced is the recipe's trajectory up to stage e, not the final number.

## Infrastructure lesson: RAM, not CPU — and it cost three runs
All three arms died the same way: a stage boundary spawns 7 fresh torch+pybullet workers (~4 GB
burst) and the machine has **29.7 GB RAM** (not the 32 *cores* I reasoned from when deciding to
run three ladders). Symptoms are either `OSError [WinError 1114] … shm.dll` or a train log that
simply stops mid-startup with no traceback.

Worse, the monitoring was blind to it: a lingering selection process plus a legitimately stale
training log (selection is single-threaded and takes 1–2 h) made a dead ladder look identical to
a healthy one — **xw84 went unnoticed for 8 hours**.

Fixes now in place:
1. **Concurrency cap of 2** (user instruction, and independently justified by the RAM math).
2. **Retry loop in every ladder** — 3 attempts, 180 s pause (`run_stage()` in
   `run_xw87_eplen.sh`). It works: xw87 hit a spawn failure at 17:28 and recovered.
3. **Health checks grep for `Traceback|OSError|WinError`** and for a `FAILED` line, instead of
   trusting process existence and log age.

## Where this leaves the campaign
Four mechanisms tried since the plateau, none beat 2.97: wind oversampling (null), capacity
(behind), rate interface (tie, trial 83), tilt-cap extension (refuted, trial 83). The recipe
looks genuinely at its ceiling near **3 m/s pooled / 25% <1**, with hover and low at goal and the
fast bands unresolved after seven eliminated explanations for the descent asymmetry.
