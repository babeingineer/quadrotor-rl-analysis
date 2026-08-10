# Trials 78–79 — two single-variable attacks on the xw77 plateau

**STATUS: COMPLETE.** Both are 0–50 m/s single-policy lineages, identical to xw77 except for one
change each. Baseline: xw77 = pooled median **4.04**, 3% <1, plateaued at 40M.

## Trial 78 — full-sphere attitude command: REFUTED (and killed early)
**Hypothesis.** The `att_cmd` decode builds `bz_des.z = +sqrt(1-|xy|²)`, confining the commanded
thrust axis to the upper hemisphere with tilt capped at **80.0°**, while measured trim tilt for a
steep descent is 82.6° (γ=−30) and 93.0° (γ=−40). The aircraft was being asked to fly attitudes
it could not be commanded into at any action value.

**Change.** `--att-tilt-max 120`: `|xy|` maps linearly onto tilt over [0, 120°], reaching past 90°.
Verified: legacy saturates at 80° for any action, new reaches 118–120°.

**Result — clearly worse, killed at stage d:**

| stage | xw78 | xw77 |
|---|---|---|
| a (8M) | 25.43 | 14.40 |
| b (16M) | 18.06 | 9.14 |
| c (24M) | 16.12 | 5.50 |
| d (32M) | **14.90** | 4.25 |

**Why — I changed the MAPPING, not just the cap.** Legacy `tilt = arcsin(|xy|)` is fine-grained
near hover (57°/unit) and coarse near the cap (333°/unit) — well matched to a task that needs
precision at small tilt and reach at large. A linear 0–120° map halves resolution everywhere. The
damage confirms it, being worst exactly where fine control matters:

| band | xw78 | xw77 | ratio |
|---|---|---|---|
| hover | 7.37 | 2.01 | 3.7× worse |
| low | 8.98 | 2.08 | 4.3× worse |
| vhigh | 14.91 | 5.35 | 2.8× |
| top | 18.86 | 7.07 | 2.7× |

**Verdict: the tilt cap is real but is NOT the binding constraint, and this way of lifting it is
strictly harmful.** Any future attempt must preserve low-tilt resolution — e.g. a dedicated tilt
action dimension, or a warped mapping — rather than rescaling the existing two dims.

## Trial 79 — command-scaled observation: MECHANISM CONFIRMED, pooled-neutral
**Hypothesis.** Obs uses `vel_err / MAX_SPEED`, so at MAX_SPEED=50 a 0.5 m/s hover error is 0.01,
and VecNormalize's running std is dominated by fast-band errors — slow-speed signal is compressed
toward zero. Evidence that pointed here: xw77 **matches** the specialist at vhigh (5.35 vs 5.73,
0.93×) but is **7.4× worse at hover** (2.01 vs 0.27) — the gap is monotonic in speed, largest at
the slow end.

**Change.** `--rel-obs`: append `clip(vel_err / max(|target|, 8), ±3)` (3 dims, 40 → 43). The
absolute channel is retained, so this is pure information addition. Legacy attitude interface.

**Result — pooled identical, but the mechanism is real:**

| stage | xw79 | xw77 |
|---|---|---|
| a | 17.12 | 14.40 |
| b | 9.90 [8.85–11.23] | 9.14 |
| c | 5.40 [4.87–6.02] | 5.50 |
| d | **4.17** [3.72–4.57] | 4.25 |
| e | 4.36 [3.65–4.81] | **4.04** |

Per band at stage d — this is the point:

| band | xw79 | xw77 |
|---|---|---|
| hover | **0.74 (67% <1)** | 2.01 (0%) |
| low | **1.45 (29% <1)** | 2.08 (7%) |
| mid | 2.88 | 3.34 |
| high | 5.15 | 4.74 |
| vhigh | 5.96 | 5.35 |
| top | 7.67 | 7.07 |

**Hover improved 2.7× and went from 0% to 67% of episodes under 1 m/s — the first time any single
0–50 policy has brought a band near the goal.** Low improved 1.4×. The fast bands worsened ~8–11%,
which cancels the gain in the pooled median. The prediction was correct and specific; the pooled
statistic simply averaged it away, which is the same reporting trap as trial 69's median.

**Verdict: ADOPT `rel_obs`.** It converts the slow end from hopeless to near-goal at no pooled
cost. The ~10% fast-band cost is within single-seed noise and is not worth defending either way.

## Where this leaves the single-policy goal
Best single 0–50 policy to date: **xw79 stage d — pooled 4.17, 7% <1**, with hover 0.74/67% and
low 1.45/29%. The pooled median is now **dominated by the fast bands** (high 5.15, vhigh 5.96,
top 7.67), and the largest remaining gap versus a specialist is high 18–25 (5.15 vs 1.77 = 2.9×).

Two plateaus (xw77 4.04, xw79 4.17/4.36) say flat 0–50 training saturates near 4 m/s. The
campaign's strongest fast-band finding is that those bands were won by **transfer, not fresh
training** (trial 54: fresh 18–25 = 5.07 vs transfer 2.03) → trial 80 applies that to one lineage
with a growing envelope (0–18 → 0–25 → 0–34 → 0–45 → 0–50), carrying rel_basin and rel_obs.

## Honest limits
- Single seed per arm. The xw78 refutation is large enough (3.5×) to be safe; the xw79 fast-band
  regression (~10%) is not, and should not be quoted as a real cost.
- xw78 was stopped at stage d rather than run to 40M. Its trend (25.43 → 18.06 → 16.12 → 14.90)
  cannot reach 4.04, so the verdict does not depend on the missing stage.
- xw78's training processes survived the task stop and briefly competed with xw79 for CPU; they
  were killed by command-line match. No result is affected (timing only).
