# Trial 77 — xw77: ONE policy, ONE lineage, 0–50 m/s (the stated goal), 40M steps

**STATUS: COMPLETE.** Ran 2026-08-07 21:45 → 2026-08-08 08:58. Five stages: fresh 8M then four
+8M continuations at lr 1e-4, each resuming from the previous stage's worst-band-selected
`envelope_best` bundle.

## Why
User: *"i want to train once to get the perfect agent for all speed range"* / *"train once to
make it work for all range 0 to 50m/s"*. The banded composite (four specialists + routing) does
not satisfy this. Trial 73 attempted one 0–45 policy but only as a **4M mechanism screen**; the
band specialists needed 36M+. **Budget was the untested variable.**

## What (one lineage, all validated parts)
`--speed-min 0 --max-speed 50 --rel-basin 1.0` + standing recipe (att_cmd, yaw gate, attitude
yaw gate, precision 0.7, cov 5, wind 0–15, full DR, trim-init 0.2, ent 0.003), 6 envs.
Deliberately NOT included: descent-weighted sampling. Targets are uniform on the sphere, so 50%
of commands already have |γ|>30 — the descent deficit is not an exposure problem, and trial 03
established exposure cannot beat a reward barrier.

## Result — real progress, then a hard plateau
| stage | steps | pooled median | %<1 |
|---|---|---|---|
| a | 8M | 14.40 | 0% |
| b | 16M | 9.14 [8.67–9.67] | 0% |
| c | 24M | 5.50 [4.86–6.00] | 0% |
| d | 32M | 4.25 [3.81–4.81] | 5% |
| e | 40M | **4.04 [3.71–4.82]** | 3% |

Per-stage gain: −5.3, −3.6, −1.3, **−0.2**. Stage e's CI overlaps stage d's almost entirely —
**the ladder has plateaued at ~4 m/s**, and more of the same budget will not close it.

Final per-band (300 episodes, full DR):

| band | median | %<1 | p90 | yaw |
|---|---|---|---|---|
| hover 0–1 | 2.01 | 0% | 2.75 | 10.5° |
| low 1–10 | 2.08 | 7% | 4.87 | 14.5° |
| mid 10–18 | 3.34 | 2% | 6.89 | 26.8° |
| high 18–25 | 4.74 | 5% | 11.89 | 37.8° |
| vhigh 25–35 | 5.35 | 0% | 13.24 | 61.7° |
| **top 35–45** | **7.07** | 1% | 21.14 | 63.1° |
| ALL | 4.04 | 3% | 13.58 | crash 0.0% |

## Verdict: PARTIAL — the architecture works, the precision does not
**Versus the banded composite (pooled 1.22, 44% <1) the single policy is 3.3× worse**, and worse
in every band it shares (hover 2.01 vs 0.27, low 2.08 vs 0.44, mid 3.34 vs 0.77, high 4.74 vs
1.77). Only vhigh is comparable (5.35 vs 5.73).

Two genuine firsts, though:
1. **35–45 m/s is covered for the first time in the project** (7.07 median, 0 crashes). No
   specialist ever flew that band.
2. **The descent asymmetry largely closed.** γ sweep at 25–45: descents 6.14 vs climbs 3.77 =
   **1.63×**, against the vhigh specialist's 4.2× — and the vertical undershoot is *gone*
   (−0.75 to +1.39 m/s, versus the specialist's +6.1 m/s shortfall). So trial 75's deficit is
   **not intrinsic**; a wide-envelope policy with the basin reward mostly fixes it.

## Why it stopped at 4 m/s — measured, not guessed
The `att_cmd` decode builds `bz_des.z = +sqrt(1-|xy|²)` with `|xy| ≤ 0.985`, confining the
commanded thrust axis to the **upper hemisphere with tilt capped at 80.0°**. Measured trim tilt
for steep descent at 25–34 m/s is **82.6° (γ=−30) and 93.0° (γ=−40)** — outside the action space
at any action value. Instrumenting the vhigh specialist:

| γ | trim tilt | commanded | achieved | inner-loop track err |
|---|---|---|---|---|
| −40 | 93.0 | 63.1 | 85.5 | 28.1° |
| −30 | 82.6 | 58.6 | 66.3 | 22.4° |
| 0 | 57.9 | 57.5 | 56.2 | 22.6° |
| +40 | 34.0 | 47.5 | 44.5 | 23.1° |

At level and climb the policy commands ≈ trim; in descent it under-commands by 16–30°. Two
separate defects, both real: a hard interface cap above γ≈−30, and a learned under-command below
it. Also visible: the inner attitude loop misses its own setpoint by 22–28° at *every* flight
path angle.

→ Trial 78 changes exactly one thing: a full-sphere thrust-axis command (`--att-tilt-max 120`).

## Honest limits
- One seed. The stage-to-stage trend is strong, but 4.04 vs 4.25 is a single lineage.
- Yaw at the fast bands is 61–63°, which the spec permits (yaw free at speed), but hover/low yaw
  at 10–14° is worse than the specialists' ~3–6°.
- The plateau is established over one stage only; a 6th stage might still creep. Given −0.2 with
  overlapping CIs, further identical stages are not the efficient use of compute.
