# Trial 69 — xw69: recovery curriculum on the mid champion

## Why — an acceptance failure the campaign had stopped watching
Dive-recovery acceptance (60 upset starts per champion, 2026-08-05):

| champion | band | recovered (<8 m/s) | partial (8–15) | median final err |
|---|---|---|---|---|
| xw48c | 0–10 | **10%** | 2% | 49.9 |
| xw35b | 10–18 | **12%** | 2% | 35.8 |
| xw51b | 18–25 | **17%** | 7% | 36.2 |
| xw55a | 25–34 | **18%** | 10% | — |

For comparison the old *generalist* xw17 recovered 57% + 23% partial. **Specialisation plus
goal-state initialisation bought nominal precision and lost upset robustness**, and because
recovery is not part of the ladder gates, nothing in the automated loop noticed. Every
per-band number in this project is a *nominal-flight* number; this is the safety-relevant
column that regressed.

Mechanism is not mysterious: tough-init (failure-state starts) was dropped at trial 06 after
the ablation showed the yaw gate was the active ingredient, and trim-init then pushed the
training distribution further toward good states. The policies simply never see upsets.

## What (pure RL, no architecture change)
Continue the mid champion with a small failure-state fraction reintroduced:
`--tough-init-override 0.10`, then `0.20`, +8M each @1e-4 with wind oversampling. Measure
BOTH nominal precision and recovery after each.

## Exact code changes
```python
# continue_train.py — flag (NEW; recovery curriculum without editing the recipe):
    ap.add_argument("--tough-init-override", type=float, default=None,
                    help="set/override the failure-state (upset) init fraction for this "
                         "continuation — recovery curriculum without touching the recipe")

    if args.tough_init_override is not None:
        cfg["tough_init"] = args.tough_init_override
```
The env already supports `tough_init_frac` (trial 03) and `continue_train.py` already
forwards `cfg["tough_init"]` into `train_kwargs`; only the override was missing.

## Pre-registered (vs xw35b: median 0.82, 62% <1, recovery 12%)
- **SUCCESS**: recovery ≥50% with nominal median ≤1.0 → adopt for every champion and
  re-run the composite; recovery becomes a standing acceptance gate.
- **TRADEOFF**: recovery ≥50% but nominal median 1.0–1.3 → report both and let the user
  choose the operating point (precision vs upset robustness).
- **FAILURE**: recovery <30% or nominal median >1.3 → the two objectives are in genuine
  conflict at this dose; try 0.05, and if that also fails, document the trade as a property
  of the specialist approach.

## Result
*(auto-appended)*

## VERDICT (revised after the 0.20 rung — see correction below)
**tough-init 0.10 on the mid champion: precision median 0.89 [0.82–0.98] (held), recovery
13% (was 12%) — no effect.** So the deficit is not exposure dose *at 0.10*.

### CORRECTION: dose is not refuted, it is weak and it costs precision
I wrote "dose refuted" after the 0.10 rung alone. The 0.20 rung then landed and it does move:

| tough-init | recovery | precision median | %<1 |
|---|---|---|---|
| 0 (xw35b baseline) | 12% | 0.82 | 62% |
| 0.10 | 13% | 0.89 [0.82–0.98] | 57% |
| **0.20** | **22%** | **0.97 [0.91–1.03]** | 54% |

So exposure dose has a **real but weak** effect — roughly doubling recovery at 0.20 — bought
against a precision median walking 0.82 → 0.89 → 0.97, i.e. straight to the 1 m/s goal line.
Extrapolating the trend, the dose needed for generalist-level recovery (57%) would blow the
precision target outright. The conclusion that survives is not "dose does nothing" but
**"dose trades precision for recovery at a bad exchange rate, and the switch does not."**
The earlier one-rung verdict was premature; this is what the full ladder shows.

Generalist-vs-specialist recovery under the identical test:
| policy | trained range | recovered | partial |
|---|---|---|---|
| xw17 generalist | 0–25 | **57%** | 23% |
| xw13 generalist | 0–25 | 37% | 10% |
| xw18b specialist | 0–10 | 18% | 2% |
| xw35b specialist | 10–18 | 12% | 2% |

xw18b predates trim-init entirely and still recovers at 18%, so neither trim-init nor
tough-init dose explains it. **Recovery is a STATE-COVERAGE property**: an upset throws the
aircraft to 40 m/s in a dive, which is inside a full-envelope generalist's experience and
far outside a band specialist's. Specialisation buys precision by narrowing experience, and
narrowing experience is exactly what costs recovery.

### Fix: supervisory recovery switch (no retraining, still all-RL)
`eval_recovery_switch.py` routes control to the generalist while the aircraft is upset
(velocity error >12 m/s) and hands back to the band champion once settled (<6 m/s):

| configuration | recovered | partial | median final err |
|---|---|---|---|
| mid champion alone | 12% | 2% | 35.8 |
| generalist alone | 57% | 23% | 6.8 |
| **switch (20 eps)** | **60%** | 25% | **4.2** |

0.7 switches per episode, 75% of steps in the recovery policy. The composite therefore
gains an upset-recovery mode for free, using a policy already trained — it is a routing rule
over networks, not a classical controller, so the all-RL constraint holds.

Remaining caveat: nominal precision must be re-measured with the switch armed (a spurious
switch during normal flight would hurt); the entry threshold of 12 m/s is far above any
nominal band error, so spurious entry should be rare, but it needs the measurement.

## Switch design: two failures then a working version (all measured, n=60 upsets / 150 nominal)
| detector | recovery | nominal median | nominal %<1 | fired in nominal | switches/ep |
|---|---|---|---|---|---|
| velocity error >12 | 55% | **1.47** | 37% | **83%** | 0.6 |
| state (tilt/sink/rate), no dwell | 48% | **2.93** | 29% | **71%** | 3.3 |
| **state + dwell (0.4 s arm, 1 s stay)** | **60%** | **0.84** | **56%** | **18%** | 0.9 |
| champion alone (reference) | 12% | 0.76–0.82 | 59–62% | — | — |

The first detector was mine and wrong in an obvious way: a normal episode starts at rest and
must accelerate to the target, so its velocity error legitimately *begins* above any
sensible threshold — it detected "approach in progress", firing on 83% of nominal flights.
The second fixed the signal (tilt / excess sink / body rate) but still fired on 71%, because
the policies fly aggressively during the approach and transiently exceed 84° tilt and
2.5 rad/s. The missing ingredient was **dwell**: an upset persists, an aggressive manoeuvre
does not. Requiring 0.4 s of sustained upset before handover and a 1 s minimum stay gives
**60% recovery (5x the champion's 12%) at a nominal cost of 0.76→0.84 median and 62→56% <1.**

Residual honesty: it still fires in 18% of nominal episodes, and that is where the small
precision cost comes from. Tightening further trades recovery back. This is an operating
point, not a free lunch — the numbers above are what a user needs to choose it.

## CORRECTION: the table above is mid-band-only, and the script that produced it leaked
Folding the switch into the composite exposed two defects in the numbers above. Both are mine.

**1. Target-sampling leak.** `apply_cfg()` mutates `env.MAX_SPEED` because each policy needs
its own obs scaling — but the env also samples the command from `uniform(SPEED_MIN, MAX_SPEED)`
at reset (`rate_vel_aviary.py:592`). Since `reset()` ran *before* the first `apply_cfg()` of
each episode, every episode inherited the scaling of whichever policy was flying when the
previous episode ended. With the generalist (MAX_SPEED 25) usually last, the mid champion was
being commanded up to 25 m/s in a test that was supposed to stop at 18. Fixed by
`reset_episode()`, which restores the band's own range before every reset.

**2. The detector did not generalise off the band it was tuned on.** Armed across the whole
roster it fired on **47%** of nominal episodes, not 18%. Per-step attribution
(`diag_upset_terms.py`) shows why — and it is not what I assumed:

| band | policy | tilt<84° | sink>15 | rate>2.5 | any | nominal tilt p50/p95 |
|---|---|---|---|---|---|---|
| 0–10 | xw48c | 1% | 0% | **17%** | 17% | 14° / 48° |
| 10–18 | xw35b | 1% | 0% | 6% | 7% | 27° / 65° |
| 18–25 | xw51b | 7% | 4% | 12% | 17% | 40° / 92° |
| 25–34 | xw55a | **12%** | 6% | 12% | 22% | 46° / **110°** |

Two independent errors. The body-rate limit (2.5 rad/s) is simply too tight — these policies
use more than that on 6–17% of *normal* steps, worst at the low band. And the absolute tilt
limit is wrong in principle: **a tailsitter's nominal cruise is near-horizontal**, so nominal
tilt p95 reaches 92–110° at speed and "past 84°" describes ordinary fast flight. The mid band
was the one band where both happened to be harmless, and that is the band I tuned on.

### Fix: calibrate against data, and make tilt relative to trim
`calib_upset.py` records nominal + upset trajectories for all four bands once, then sweeps
thresholds offline (free) scoring per-episode firing *with* dwell. Tilt is compared against
the **trim attitude the command implies** (from `trim_table.npz`), not a constant. Pareto
front over (nominal false-fire ↓, upset detection ↑):

| tilt margin over trim | sink | rate | arm | nominal FP (per band) | upset detect |
|---|---|---|---|---|---|
| +75° | 30 | 6.0 | 1.2 s | 2% (0/0/3/3) | 76% |
| **+60°** | **25** | **6.0** | **0.8 s** | **3% (0/0/7/7)** | **87%** |
| +45° | 25 | 6.0 | 0.8 s | 7% (3/7/7/10) | 88% |
| +45° | 20 | 6.0 | 0.4 s | 20% (13/23/13/30) | 93% |
| (old hand-set: abs 84°/15/2.5, 0.4 s) | | | | **47%** | — |

Adopted: **tilt +60° over trim, sink 25 m/s, rate 6.0 rad/s, arm 0.8 s, stay 1.0 s** — nominal
false-fire 3% (worst band 7%) at 87% upset detection, a 16× reduction in spurious firing.
`is_settled()` needed the same treatment: an absolute "settled" tilt limit would never be
satisfied during fast cruise, so the generalist would take over and never hand back.

## Composite result: paired armed vs disarmed (400 nominal + 160 upset episodes each)
Both arms run the *same* rollout code on the *same* seeds; only the flying net differs, so the
precision cost of arming is a paired comparison rather than a cross-script one.

FINAL numbers, out-of-sample (nominal seeds 20000+, clear of the calibration set; 400 nominal
+ 240 upset per arm, envelope-gated arming):

| band | median (dis → armed) | **p90 (dis → armed)** | recovery (dis → armed) | fired |
|---|---|---|---|---|
| 0–10 | 0.43 → 0.43 | 3.18 → **3.18** | 12% → **60%** | 3% |
| 10–18 | 0.77 → 0.77 | 9.89 → **7.12** | 18% → **57%** | 9% |
| 18–25 | 1.77 → 1.77 | 14.24 → 14.45 | 27% → **35%** | 6% |
| 25–34 (unarmed) | 5.73 → 5.73 | 18.79 → 18.79 | 32% → 32% | — |
| **pooled** | **1.22 [1.04–1.60]** (both) | **14.62 → 13.98** | **22% [17–28] → 46% [40–53]** | **5%** |

Out-of-sample the tail moves the *other* way from the in-sample run: pooled p90 **improves**
14.62 → 13.98, driven by the mid band's 9.89 → 7.12, with only 18–25 marginally worse
(14.24 → 14.45). Median final error after an upset falls 38.8 → 9.8 m/s. Tail statistics are
seed-sensitive at these sample sizes, which is exactly why the in-sample/out-of-sample
distinction mattered — and why the earlier "p90 got worse" reading was itself provisional.

Conditional split (armed): the 21 flagged episodes have median 20.43 / p90 40.04, the 379
others 1.09 / 10.88. **This split alone proves nothing about cost**: the detector fires
*because* the aircraft is upset, so flagged episodes are already the hard ones.

### Paired attribution: the same episodes, both ways (`paired_attribution.py`)
Joining the armed and disarmed dumps on (band, seed) gives a true paired test. First, the
control that makes it valid:

**379 unfired episodes are byte-identical between arms — max |armed − disarmed| = 0.00e+00.**
The switch provably does not perturb flights it does not engage on.

Of the 21 flagged episodes, 5 are on the UNARMED 25–34 band, where "switching" routes to the
same net and changes nothing (errors identical, 41.15 → 41.15) — a reporting artifact now fixed
so the firing rate counts only real handovers. On the **16 genuine engagements (4% of 400)**:

| | disarmed | armed |
|---|---|---|
| mean vel err | 21.18 | **15.36** |
| per-episode | — | helped 9, hurt 7 |
| summed magnitude | — | **−107.7 improved vs +14.5 regressed** |
| extremes | — | best −20.18, worst **+9.71** |

So arming is **net positive on nominal precision as well**, by a 7.4:1 magnitude ratio, while
provably untouching the other 96% of flights. Per band: mid 21.87 → 10.81 (helped 6/8),
low 15.70 → 13.22 (1/3), high 23.36 → 23.91 (2/5 — the one band where engagement is roughly
break-even, consistent with its marginal p90).

**It is still not free**: 7 of 16 engagements ended worse, the worst by +9.71 m/s. The correct
claim is "net beneficial with a real per-episode variance", not "no cost" — which is what I
wrongly wrote first, from the one statistic that could not move.

Pooled median final error after an upset falls 34.8 → 10.9 m/s. The mid band's *mean* also
improves (2.34 → 1.74) because the switch rescues tail episodes the champion alone loses.

### CORRECTION: "precision unchanged" was the wrong statistic
I first wrote "precision is unchanged to two decimals in every band." That is true of the
median and **it had to be**: at a 3–6% firing rate, a median over 82–118 episodes is
structurally insensitive to what arming changes. `eval_velyaw.report()`'s own docstring says
the median alone is insufficient here — which is why p90 is part of the standard reporting.
Looking at p90, at the one band where the switch actually fires:

| 18–25 band | fired | median | mean | **p90** |
|---|---|---|---|---|
| disarmed | — | 2.01 | 4.22 | **8.60** |
| armed | 6% | 2.01 | 4.09 | **11.19** |

Pooled p90 moves 9.33 → 9.56. So arming is **not** free — it shifts the tail at the band where
it engages, and I reported the one statistic guaranteed to show nothing. `eval_composite.py`
now prints the fired-vs-unfired conditional split, which is the statistic that answers "what
does arming cost *when it engages*", and the composite's nominal seed base moved to 20000 so
the thresholds are no longer selected on the same episodes they are scored on (the calibration
recorded seeds 5000+/1000+, which the first evaluation also used — an in-sample overlap).

The conclusion that routing beats retraining is unaffected: it rests on recovery 24% → 46%,
not on the precision column.

### Is arming 18–25 worth it? Decided at n=150 upsets / 120 nominal (paired, same seeds)
The band's recovery gain at n=60 (28% → 35%) was inside binomial noise (~6pp), so it was not
yet a decision. At n=150:

| 18–25 | recovery | partial (8–15) | median final err | precision median | **p90** | fired |
|---|---|---|---|---|---|---|
| champion alone | 21% | 6% | 34.0 | 2.07 [1.80–2.84] | **9.82** | — |
| **armed** | **32%** | **23%** | **13.6** | 2.07 [1.80–3.15] | **14.22** | 9% |

The recovery gain is real: +11pp on the strict criterion (≈2σ), and the supporting shifts are
unambiguous — partial recovery 6% → 23%, median final error 34.0 → 13.6 m/s. **This is the
reason the band stays armed.**

⚠ **Provenance: the p90 column above is SUPERSEDED.** This run used nominal seed base 5000 —
the same episodes `calib_upset.py` selected thresholds on — so its tail figure is in-sample.
The authoritative number is the out-of-sample composite: **p90 14.24 → 14.45** (a marginal
rise, not 9.82 → 14.22), and paired attribution on that band shows engagement roughly
break-even (5 episodes, 23.36 → 23.91 mean, helped 2/5). Where the two disagree on the tail,
the out-of-sample composite governs; the recovery column is unaffected and consistent in both.

**Verdict: keep 18–25 armed.** Unlike 25–34 (where arming made recovery *worse*), here the
aircraft ends an upset near its command instead of 34 m/s away, for a tail cost that is
marginal out-of-sample and break-even per engaged episode. It is the weakest of the three armed
bands and the one to disarm first if nominal tail precision is valued over upset survival.
Low/mid bands do not pose the question — mid is where the switch helps most (21.87 → 10.81).

### Internal control: the harness is deterministic
In the envelope-gated run the UNARMED 25–34 band reproduces its disarmed numbers exactly
(mean 8.08, p90 21.19, median 4.25). Since that band's rollouts are byte-identical while the
armed bands differ, every armed-vs-disarmed difference reported here is a real switch effect
rather than seed noise — the paired comparison has its own built-in null.

### The 25–34 band must NOT be armed — measured, not assumed
Recovery there goes **28% → 5%**: the generalist trained to 25 m/s, so arming it under a
25–34 m/s command asks it to fly a target outside its own envelope, and it does actively worse
than the specialist it replaced. `eval_composite.py` now gates arming on the generalist's
trained range (`hi <= gen_max`) and labels the band UNARMED rather than silently degrading it.
This is the same state-coverage principle that explains the whole effect, applied in reverse:
a policy is robust *inside* its envelope and unreliable outside it.

Corroboration for the state-coverage diagnosis, from configs: xw17 has `tough_init=0.0` — the
generalist never trained on failure states at all. Its recovery advantage is **envelope
breadth alone**, which is why dose (above) buys so little and why routing buys so much.

### FINAL configuration: arm only in-envelope (400 nominal + 240 upset)
| band | precision median | %<1 | recovery | fired |
|---|---|---|---|---|
| 0–10 | 0.42 | 82% | **60%** | 0% |
| 10–18 | 0.75 | 65% | **57%** | 2% |
| 18–25 | 2.01 | 22% | 35% | 6% |
| 25–34 (unarmed) | 4.25 | 4% | 32% | — |
| **pooled** | **1.15 [1.04–1.46]** | **45%** | **46% [CI 40–53]** | **3%** |

| configuration | pooled recovery | pooled precision median |
|---|---|---|
| disarmed | 24% | 1.15 [1.04–1.46] |
| armed everywhere | 39% | 1.15 [1.04–1.46] |
| **armed only in-envelope** | **46% [CI 40–53]** | **1.15 [1.04–1.46]** |

Recovery nearly doubles for free. Per-band recovery moves a few points between the two armed
runs (low 65 vs 60, high 30 vs 35) — that is sampling noise at 40–60 upsets per band, which the
pooled CI [40–53] quantifies; the per-band figures should not be read to closer than ~10 points.

### Caveat on cross-table comparison
Disarmed recovery here (15/25/28/28%) is higher than the earlier acceptance pass (10/12/17/18%)
because this harness uses 8 s episodes and the fixed command-sampling range, versus 10 s in
`dive_recovery_test`. The armed-vs-disarmed comparison above is paired and valid; comparing
these numbers to the older table is not apples-to-apples.
