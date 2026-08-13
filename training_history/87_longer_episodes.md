# Trial 87 — xw87: 16 s episodes — NEW BEST single policy (settling margin pays at the fast bands)

**STATUS: COMPLETE.** 3 stages (+24M) continuing `results_velyaw_xw80_h` with `--episode-len 16`
(vs the standing 8 s). Finished 2026-08-13 02:21. Survived one RAM-spawn failure via the retry
loop (first ladder to do so).

## Why
The worst band is top 35–45 at 9.79, and it has the least settling margin: at 45 m/s an 8 s
episode leaves ~5 s to build full speed from rest before the 3 s scoring window opens. Trial 75
tested 20 s episodes but only on band *specialists* and only for the descent question — never on
the single 0–50 policy. Episode length is a protocol/distribution change → continuation-safe
(trial 81's lesson: action semantics are not, but this is not that).

## Result — first clear move past the ~3 m/s plateau
Scored at BOTH protocols; the 8 s scores are the comparable ones:

| stage | @8 s median | %<1 | @16 s median | %<1 |
|---|---|---|---|---|
| a | 2.99 [2.45–3.66] | 23% | 3.03 | 25% |
| b | 2.77 [2.14–3.22] | 26% | 2.64 | 27% |
| c | **2.62 [2.06–3.32]** | **25%** | 2.63 | 27% |

Trajectory still falling at the ladder's end → continued as xw88.

Per band (stage c @8 s) vs the old best:

| band | xw87_c | xw80_h | change |
|---|---|---|---|
| hover 0–1 | **0.35** (83%) | 0.41 (83%) | −15% |
| low 1–10 | **0.46** (81%) | 0.56 (81%) | −18% |
| mid 10–18 | 1.37 (36%) | 1.25 (36%) | +10% (noise) |
| high 18–25 | **1.84** (10%) | 2.28 (15%) | −19% |
| vhigh 25–35 | **4.63** (3%) | 5.58 (1%) | −17% |
| **top 35–45** | **7.09** (2%) | 9.79 (1%) | **−28%** |
| pooled | **2.62** / 25% | 2.97 / 25% | −12% |

**Five of six bands improved, and the gain is largest exactly where the hypothesis said it
should be** — the fast bands, where settling margin binds hardest. Yaw also improved at the fast
end (top 40.8° vs 63–74° historically). Crash rate 0%.

## Interpretation, with a caveat
The mechanism is presumably that 16 s episodes let the policy *experience* the settled regime at
high speed (an 8 s episode at 45 m/s is mostly transition), so the reward finally pays for
holding trim there — the same reason trim-init worked (trial 27), delivered through the episode
protocol instead of the initial state.

Caveat: because training AND the returns changed together (longer horizon at the same γ=0.99),
this bundles "more settled-state exposure" with "effectively longer credit horizon". The 8 s
evals show the benefit transfers to the short protocol, so it is not an artifact of scoring —
but which half of the bundle does the work is not isolated.

## Verdict: ADOPT. New deliverable candidate is xw87_c (formally superseded by xw88's best stage
once that ladder lands). The prior baseline xw80_h stands only as the 8 s-protocol reference.

## Honest limits
- Single seed, as always in this campaign; the pooled −12% is inside overlapping CIs, but the
  consistent per-band pattern (5/6 improved, biggest where predicted) is the actual evidence.
- Mid regressed 10% — within noise, but watch it across xw88's stages for a real drift.
- The goal (<1 m/s everywhere) is still not met: mid 1.37, high 1.84, vhigh 4.63, top 7.09.
