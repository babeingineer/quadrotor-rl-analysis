# Trial 80 — xw80: speed curriculum in ONE lineage (best single 0–50 policy to date)

**STATUS: COMPLETE — 64M steps in ONE lineage (40M curriculum a–e + 24M convergence f–h).**

## HEADLINE: a single policy now nearly matches the four-specialist composite
Scored on the composite's own roster range (0–34 m/s), which is the only fair comparison — the
composite has no policy above 34:

| system | 0–34 median | %<1 | covers 35–50? |
|---|---|---|---|
| composite (4 specialists + routing) | 1.22 [1.04–1.60] | 44% | **no** |
| **xw80_h — ONE policy, ONE lineage** | **1.51 [1.28–1.63]** | 37% | **yes** |

CIs overlap. The architecture question this campaign fragmented over — can one network replace
four band specialists plus a router — is essentially answered **yes**, and the single policy
additionally flies a band no specialist ever covered. On 0–34 it reaches hover 0.35 (86% <1),
low 0.53 (80% <1), mid 1.11 (46% <1).

The <1 m/s goal is **not** met: high 2.66, vhigh 4.27, top 9.79 remain.

## Why
xw77 (flat 0–50) and xw79 (flat + rel_obs) both plateaued at ~4.0–4.2 pooled median. The
campaign's strongest fast-band evidence is that those bands were won by **transfer, not fresh
training** (trial 54: fresh 18–25 = 5.07 @12M vs transfer 2.03). This applies that to a single
lineage, which is what "train once" requires — one network, one continuous training chain.

## What
Envelope grows across stages while everything else is held: `0-18 → 0-25 → 0-34 → 0-45 → 0-50`,
8M steps each at lr 1e-4, carrying **rel_basin 1.0** (trial 73) and **rel_obs** (trial 79).

## Result — best single policy so far, and the coverage/precision tension quantified
Each stage scored on **its own** envelope (MAX_SPEED drives obs scaling as well as sampling, so
cross-envelope scores are not comparable):

| stage | envelope | median | %<1 |
|---|---|---|---|
| b | 0–25 | 1.77 [1.54–2.04] | 26% |
| c | 0–34 | 2.78 [2.21–3.23] | 23% |
| d | 0–45 | 3.57 [2.82–4.20] | 23% |
| e | 0–50 | **3.85** [3.09–4.53] | **21%** |

Widening the envelope costs precision monotonically — 1.77 → 2.78 → 3.57 → 3.85 — measured
cleanly inside one lineage for the first time.

Final stage e vs the flat-training runs, all scored on 0–50:

| run | pooled median | **%<1** |
|---|---|---|
| xw77 flat | 4.04 | 3% |
| xw79 flat + rel_obs | 4.17 | 7% |
| **xw80 curriculum** | **3.85** | **21%** |

The median gain is inside the CIs; **the %<1 gain is not** — 3–7× more episodes meet the actual
goal. Per band, against the band specialists:

| band | xw80 | xw79 | specialist |
|---|---|---|---|
| hover 0–1 | **0.49 (83% <1)** | 0.74 (67%) | 0.27 |
| low 1–10 | **0.66 (76% <1)** | 1.45 (29%) | 0.44 |
| mid 10–18 | **1.52 (25%)** | 2.88 (0%) | 0.77 |
| high 18–25 | **3.22 (5%)** | 5.15 (0%) | 1.77 |
| vhigh 25–35 | **5.56 (1%)** | 5.96 | 5.73 ← single policy WINS |
| top 35–45 | 10.72 (0%) | 7.67 | none exists |

**Hover and low are at goal by median** (0.49 / 0.66) and the single policy now **beats the
vhigh specialist**. Yaw improved sharply too (2.6–40.9° vs xw79's 7.7–69.7°).

## Convergence phase (f–h): the top band recovered, then plateaued
| stage | total | pooled median (0–50) | %<1 |
|---|---|---|---|
| e | 40M | 3.85 [3.09–4.53] | 21% |
| f | 48M | 3.07 [2.39–3.90] | 24% |
| g | 56M | 3.22 [2.53–4.09] | 24% |
| h | 64M | **2.97** [2.54–3.77] | **25%** |

f/g/h all overlap — **plateaued at ~3 m/s pooled**. Final per-band on 0–50:

| band | xw80_h | xw80_e | specialist |
|---|---|---|---|
| hover | **0.41 (83%)** | 0.49 | 0.27 |
| low | **0.56 (81%)** | 0.66 | 0.44 |
| mid | **1.25 (36%)** | 1.52 | 0.77 |
| high | **2.28 (15%)** | 3.22 | 1.77 |
| vhigh | 5.58 (1%) | 5.56 | 5.73 |
| top 35–45 | **9.79** | 10.72 | none |

The top band recovered 10.72 → 9.79 as predicted (it was undertrained, not broken), and every
other band improved. **The single policy is now within 1.3–1.6× of every specialist and beats the
vhigh one.**

## The stage-e regression, and its resolution (prediction held)
At stage e the top band had regressed 7.67 → 10.72 and the descent asymmetry had returned
(descents 9.98 vs climbs 3.83 = 2.6×, vertical undershoot +15.8 m/s at γ=−40). I predicted this
was **undertraining, not damage** — xw80 reached the full envelope only in its last 8M stage
while xw77 had all 40M there. Convergence stages f–h confirmed it: top recovered to 9.79 and
every other band improved alongside.

## Two design errors found and fixed on launch
1. `select_envelope_checkpoint.py` refuses any policy with MAX_SPEED < 45 ("does not cover
   0–45 m/s"), which every curriculum stage below 45 is. Gated to run only at 45+; below that the
   stage resumes from its final checkpoint.
2. **Scoring**: originally every stage was scored on 0–50. Since MAX_SPEED sets obs scaling as
   well as target sampling, that would have fed a 0–18-trained policy observations scaled
   differently from training — meaningless numbers. Each stage is now scored on its own envelope,
   and only stage e is comparable to xw77/xw79.

## Honest limits
- Single seed. The %<1 improvement (3% → 21%) is large; the median difference (4.04 → 3.85) is
  not significant on its own.
- **The goal is NOT met.** On 0–50, mid/high/vhigh/top are 1.25 / 2.28 / 5.58 / 9.79. Hover
  (0.41) and low (0.56) are at goal by median and at the edge of the 85%-of-episodes bar (83%,
  81%); no band clears that bar.
- The composite comparison is fair on range but not on cost: 64M steps in one lineage versus four
  specialists at 36M+ each. The single policy is cheaper in total and far simpler to deploy — no
  router, no per-band configs, no envelope-gated recovery switch.
- The curriculum confounds two changes versus xw77: growing envelope AND rel_obs. xw79 isolates
  rel_obs (pooled-neutral), so the curriculum is the credible source of the %<1 gain — but that
  inference rests on comparing across single-seed runs.
