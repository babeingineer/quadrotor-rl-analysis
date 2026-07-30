# Trial 21 — PROBE (no training): classical "manual-control" baseline

| | |
|---|---|
| script | `classical_baseline.py` (velocity P+TRUE-integral + observer feedforward → force vector → attitude P → rate loop; policy-visible sensors only) |
| date | 2026-07-30 |
| trigger | user: "if we can do it manually, we can do it using RL, isn't it?" |
| tuning cost | 19 gain configs, no learning. Winner: kp=0.6 ki=0.15 katt=1.8 ff=0.2 |

## Results (full spec: wind 0–15, ALL DR incl. ±20% aero)
| | 10 s episodes | 20 s | 30 s |
|---|---|---|---|
| low (1–10) | 1.48 | **0.65 / yaw 0.1°** | **0.64 / 0.0°** |
| mid | 9.1 | 20.4 | 20.0 |
| high | 9.4 | 27.3 | **33.8 (diverges)** |

## Findings (major)
1. **User's premise CONFIRMED for the low band**: classical feedback + true integral +
   settle time achieves **0.64 m/s under the full spec** — the ±20% aero does NOT prevent
   precision tracking; identification is unnecessary for steady state at low speed.
2. **Protocol artifact exposed**: same controller 1.48→0.65 with settle time. RL specialist
   re-scored at 20 s: **1.98→2.00 — stuck**. Diagnosis: (a) the policy's LEAKY integrator
   (τ=3 s) mathematically bounds steady error (err≈I/τ); (b) trained horizon 8–10 s never
   taught settling. → trial 22 fixes both.
3. **Premise REFUTED for mid/high bands**: the classical cascade goes UNSTABLE at speed
   (error grows with episode length). Wing-borne flight under ±20% aero + wind is genuinely
   hard control, not an RL artifact. Triangle experiments (trials 18/20) remain the tool.
4. RL-vs-classical gap in the low band (2.0 vs 0.65) = concrete headroom; residual-RL
   (classical backbone + learned correction) queued as the architecture if trial 22 falls short.

---

## ADDENDUM (user challenge: "human can't control it?") — the elevator was missing
The original classical controller NEVER USED THE ELEVONS (fins pinned at 0) — it flew the
high-speed regime with its elevator bolted neutral, which no human would do. Fixes tested:
1. Gain scheduling alone (human trick #1, smaller inputs at speed): **did NOT help**
   (13.9 → 14–28). The hover paradigm is structurally wrong at speed regardless of gain.
2. **Elevator assist (human trick #2)**: symmetric elevon follows the pitch command
   (`fin = kfin·pqr[1]`, kfin=1). Mid+high: **13.9 → 6.37** — halved, and better than the
   RL high-band specialist (8.9).
3. Full envelope with one fixed elevator-equipped config (80 eps, 20 s, full spec):
   **5.30 mean / 1.48 median / 42% < 1 m/s** (low 2.22, mid 5.04, high 9.99) — a 60-line
   formula ties the best RL generalist (5.26). A band-blended classical (low-config under
   10 m/s + elevator-config above) would project to ≈4.6.

Conclusions: (a) the user's manual-control premise survives — with the right technique per
regime, simple controllers match RL; (b) BOTH approaches still degrade with speed the same
way (~2 / ~5 / ~10) — the remaining difficulty at speed is in the task physics (wind draws +
aero uncertainty at high Q), not in who is flying; (c) residual RL on the elevator-equipped
classical backbone is now a highly credible architecture.

## ADDENDUM 2 — mid-band ceiling probe (30 s, tuned, elevator-equipped)
Mid band (10–18): mean 4.97 BUT **median 0.20 m/s, 60% of episodes < 1** — when the fixed-gain
controller stays stable, patience + integral settles to ~zero even at speed. The mean is
destroyed by a minority of DR/wind draws that destabilize FIXED gains. → The task is doable at
speed; the residual is ROBUSTNESS ACROSS DRAWS — exactly what RL trains for. (User's premise
extends to the mid band.)

## ADDENDUM 3 — HIGH-band ceiling probe (30 s, tuned, elevator)
Best of 5 configs: mean 7.55, **median 3.90, 26% < 1 m/s**. Unlike the mid band (median
0.20), the TYPICAL high-band episode carries ~4 m/s even when stable — consistent with
persistent oscillation at high Q rather than steady offset (a true integral would null a
constant error). 26% of episodes still settle < 1 → favorable draws are perfectly trackable;
the high band is neither proven <1-doable nor proven impossible. Demonstrated ceiling: ~3.9
median.

## ADDENDUM 4 — high-band residual DIAGNOSED (corrects Addendum 3's oscillation guess)
Three measurements (2026-07-30):

**1. The residual is a CONSTANT OFFSET, not oscillation.** Per-episode characterization
(last 20 s of 30 s, best config): stable episodes sit at 3.2/5.7/3.8/3.7 m/s mean with
oscillation std only **0.02–0.16 m/s** — rock steady. One episode (favorable draw) settled
to 0.77. A true integrator should null any constant offset... unless saturated — and it was:
`int_clamp=8` × ki=0.25 × m ≈ **28 N of integral authority** vs 50–150 N of unmodeled
high-Q aero force.

**2. But raising the clamp makes it WORSE — an authority/windup dilemma.** int_clamp sweep
(high band, 30 eps, 30 s): 8→**8.40**, 20→11.44, 40→24.95, 80→38.35. Big integrals wind up
during the long high-speed transient and destabilize. Conditional integration (freeze while
|e|>gate) also fails (median 8.0): episodes plateauing at 3–6 m/s never engage the integral
(chicken-and-egg). The dilemma is structural to the fixed-gain cascade: the attitude the
integral demands couples back into the aero force (attitude→aero→F_des→attitude loop).
An RL policy learns this mapping directly and does not share the dilemma.

**3. ~10% of high-band draws are PHYSICALLY infeasible.** Trim-feasibility scan (per eval
seed: min residual force over 4000 attitudes × 5 elevator settings at exact target velocity,
thrust ≤ 440 N): 27/30 draws have a trim (residual ≤0.5 m/s²); 3/30 (seeds 7, 10, 14 —
target 23–23.5 m/s + adverse wind, trim airspeed 24–34 m/s) have min residual 0.5–1.0 m/s²:
drag exceeds the thrust envelope, NO controller can hold the target. The band MEAN can never
reach <1; the correct high-band success metric is **median / %<1 over the feasible ~90%**.

Verdict for "<1 m/s at high band possible?": **yes for ~90% of draws (trim exists +
26% already demonstrated), physically impossible for ~10%**. The gap between "trim exists"
and "controller finds it" is a robustness problem — the kind RL trains for. xw24 tests it.

## ADDENDUM 5 — CORRECTION: the "~10% infeasible" claim in Addendum 4 was FALSE
User challenged it ("when alpha is small, the force isn't that big") — and was right.
Measured: at Va=34, small-alpha drag in the ported model is only **16–20 N** (lift 64–172 N,
carries the 136 N weight at alpha~7deg) — nowhere near the QS=708 N scale. Re-checked the 3
flagged seeds with fine local optimization (Nelder-Mead on rotation-vector + elevator from the
best coarse sample): **all 3 refine to residual 0.000 m/s² — exact trims exist.**
The coarse scan's 0.5–1.9 m/s² residuals were RESOLUTION ARTIFACTS: 4000 random attitudes
leave ~2 deg gaps, and the force gradient at high Va (~Q·S·CY_alpha ≈ 2000 N/rad) turns 2 deg
into a fake ~1 m/s² — which is exactly why the artifact correlated with high trim airspeed.

**Corrected verdict: 100% of high-band draws are physically feasible (30/30 trims exist,
drag at trim is tens of N vs 440 N thrust). <1 m/s at the high band has NO physics
obstruction; the entire gap is controller robustness — finding and holding the trim across
DR/wind draws. Mean <1 is back on the table as a legitimate target.**

## ADDENDUM 6 — worst-corner trim check (user: "<1 at FULL 25 m/s possible?")
The envelope's absolute worst corner, checked directly: target 25 m/s + 15 m/s DIRECTLY
adverse wind (trim airspeed 40 m/s), heaviest mass 14.1 kg, aero coefficients at both ±20%
DR extremes, plus a vertically-adverse case (v_rel=[25,0,15]): **all refine to residual
0.000 m/s² — exact trims exist everywhere in the spec.** Small-alpha aerodynamics is why
(user's insight): at Va=34, the ported model gives only 16–20 N drag at small alpha with
lift 64–172 N (weight 136 N carried at alpha≈7°) — tens of N against the 440 N thrust
budget. **No target/wind/DR combination in the spec is physically untrackable.**
