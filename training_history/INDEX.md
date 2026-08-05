# Training history — velocity + heading (velyaw) task

**Quick read: [JOURNEY.md](JOURNEY.md)** — concise summary of the 81.7 → 0.44 m/s arc:
what failed, what succeeded, and the recurring failure mode.
**Negative results: [ELIMINATED.md](ELIMINATED.md)** — every mechanism tested and refuted, with
numbers, so nothing gets re-tested. Read it before proposing anything.
**Master plan: [ULTIMATE_PLAN.md](ULTIMATE_PLAN.md)** — 2026-07-31 full-record diagnosis
(4 root causes, adversarially verified) + the staged redesign to <1 m/s.

One MD file per training run, in chronological order. Each file records: what changed vs the
previous run, why, the exact code changes, the full configuration, the results (training curve,
physical metrics, behavior traces), and the analysis/verdict.

| # | file | run dir | env / key change | result (vel err / yaw err / dive recovery) |
|---|------|---------|------------------|---------------------------------------------|
| 00 | [00_velyaw_baseline.md](00_velyaw_baseline.md) | `results_velyaw` | light tailsitter, flat-plate aero (no moment) | trained OK, never physically evaluated (superseded by XWing physics) |
| 01 | [01_xwaero_motors_only.md](01_xwaero_motors_only.md) | `results_velyaw_xwaero` | **XWing aero model** + XWing airframe, motors only | **81.7 m/s** / 5.9° / — (yaw-only dive local optimum) |
| 02 | [02_xw6_elevons.md](02_xw6_elevons.md) | `results_velyaw_xw6` | **+2 elevon actuators** (6-dim action), 110 N motors | **41.3 m/s** / 2.1° / — (dive attractor persists) |
| 03 | [03_xw7_tough_init_wind_curriculum.md](03_xw7_tough_init_wind_curriculum.md) | `results_velyaw_xw7` | **+30% tough init, wind curriculum** | **39.7 m/s** / 1.7° / **0%** (exposure ≠ learning; reward identified as the trap) |
| 04 | [04_xw8_yaw_gate.md](04_xw8_yaw_gate.md) | `results_velyaw_xw8` | **+yaw-gated reward**, ent_coef 0.003 | **9.2 m/s** / 20.8° / **43%+25%** ← breakthrough |
| 05 | [05_xw8b_continuation.md](05_xw8b_continuation.md) | `results_velyaw_xw8b` | continuation 8M → 14M, unchanged config | **7.36 m/s** / **13.7°** / **47%+20%** — current best; plateaued ~13M |
| 06 | [06_xw10_gate_only_ablation.md](06_xw10_gate_only_ablation.md) | `results_velyaw_xw10` | **ABLATION**: gate only — xw7's tough-init + wind curriculum removed | **7.89 m/s** / 21.6° / 43%+15% — **gate alone is the active ingredient**; drop tough-init/curriculum |
| 07 | [07_xw11_precision_finetune.md](07_xw11_precision_finetune.md) | `results_velyaw_xw11` | **LOOP iter 1** (target <1 m/s): narrow precision peak + LR 1e-4 fine-tune of xw10 | **7.53 m/s** (low 3.79 ✓, high 13.3 ✗) — precision helps low band only; high band = strategy problem |
| 08 | [08_xw12_yaw_attitude_gate.md](08_xw12_yaw_attitude_gate.md) | `results_velyaw_xw12` | **LOOP iter 2**: attitude-gated yaw — release yaw in wing-borne flight | **6.82 m/s** / 16.2° — new best; high band 13.3→10.9, α drifting toward alignment |
| 09 | [09_xw13_fresh_fullstack.md](09_xw13_fresh_fullstack.md) | `results_velyaw_xw13` | **LOOP iter 3**: fresh 12M, full validated stack | **6.70 m/s** / **4.1°** — best overall; yaw solved; velocity floor ~6.7 across 3 lineages |
| 10 | [10_xw14_capacity.md](10_xw14_capacity.md) | `results_velyaw_xw14` | **LOOP iter 4**: capacity probe 512×512 | INTERRUPTED @2.5M (session teardown) — folded into trial 11 |
| 11 | [11_xw15_realspec.md](11_xw15_realspec.md) | `results_velyaw_xw15` | **LOOP iter 5**: REAL SPEC (wind 0–15) + 512×512 | **5.55 m/s** / 5.6° — tie w/ xw13@real-spec; capacity ruled out; loitering equilibrium found (coverage subsidy) |
| 12 | [12_xw16_cov_width.md](12_xw16_cov_width.md) | `results_velyaw_xw16` | **LOOP iter 6**: coverage width 12.5 → 5 m/s | **5.44 m/s** / 4.6° final (low 2.27 ✓) — small gain, plateaued; reward rungs exhausted; recovery eroded 20% |
| 13 | [13_xw17_transition_economics.md](13_xw17_transition_economics.md) | `results_velyaw_xw17` | **LOOP iter 7**: γ 0.997 + 14 s eps | **5.26 m/s** — new best; high 8.58 + recovery 57% (both best); **yaw collapsed 55°**; curve still rising |
| 14 | [14_xw17b_continuation.md](14_xw17b_continuation.md) | `results_velyaw_xw17b` | **LOOP iter 8**: continue xw17 +8M | **6.24** — REGRESSED (post-saturation drift); generalist track closed at xw17's 5.26 |
| 15 | [15_xw18_lowband_specialist.md](15_xw18_lowband_specialist.md) | `results_velyaw_xw18` | **LOOP iter 9 — FEASIBILITY PROBE**: 0–10 m/s specialist | **2.31** ≈ generalist's 2.27 — floor is ENVIRONMENTAL: DR costs ~1.3, wind adds ~0.7; <1 unreachable under current spec |
| 17 | [17_xw19_highband_specialist.md](17_xw19_highband_specialist.md) | `results_velyaw_xw19(b)` | **LOOP iter 11**: HIGH-band specialist + convergence | **10.09** — worse than generalist's 8.58; traces: attitude oscillation + vz drift at high Q → inner-loop branch |
| 18 | [18_lstm_full_envelope.md](18_lstm_full_envelope.md) | `results_velyaw_lstm(3)` | RecurrentPPO full-envelope — implicit system-ID vs ±20% aero DR (user request) | **FAILURE: 17.20 / yaw 82°** @6M — LSTM decisively worse than MLP; memory/system-ID path closed |
| 23 | [23_xw23_midband_corrected.md](23_xw23_midband_corrected.md) | `results_velyaw_xw23(b)` | **LOOP**: mid band, corrected recipe @ γ 0.997 | **FAILURE: 10.51 / yaw 77°** @20s — never settles; true-int obs railing + 20 s dilution suspected → isolation ladder (25/26) |
| 21 | [21_classical_baseline.md](21_classical_baseline.md) | `classical_baseline.py` | **PROBE**: manual-control baseline (user's premise) | **low 0.64 / mid median 0.20 / high median 3.90 @20-30s FULL SPEC**; high-band residual = saturated-integrator CONSTANT offset (authority/windup dilemma, structural to the cascade); trim scan (CORRECTED, addendum 5): **100% of high-band draws have an exact trim** — coarse-scan "infeasible 10%" was an attitude-resolution artifact; no physics obstruction to <1 anywhere in the envelope |
| 22 | [22_xw22_true_integrator.md](22_xw22_true_integrator.md) | `results_velyaw_xw22(b)` | **LOOP**: true integrator + 20 s + γ 0.999 + stiff gains, low band (4 vars at once) | **FAILURE: 2.66 / median 2.08 / 3%<1, yaw 53°** @20s eval — regressed vs xw18b (0.82 med); γ≈1 yaw collapse; lesson: one variable per trial → xw25 isolates |
| 24 | [24_xw24_highband_corrected.md](24_xw24_highband_corrected.md) | `results_velyaw_xw24(b)` | **LOOP**: HIGH band, corrected recipe @ γ 0.997 | **ABORTED pre-verdict** — recipe went 0-for-2 (trials 22/23); redesign waits for the isolation verdicts |
| 25 | [25_xw25_lowband_isolation.md](25_xw25_lowband_isolation.md) | `results_velyaw_xw25(b)` | **ISOLATION**: xw18b + ONLY true integrator + 20 s (γ 0.99, default gains) | **vel 0.93 med ≈ xw18b (pair EXONERATED on velocity) but yaw 90° at γ0.99** → γ never the yaw driver; E4 dead; standing recipe = leaky τ3 / 8 s / γ0.99 |
| 27 | [27_xw27_trim_init.md](27_xw27_trim_init.md) | `results_velyaw_xw27(b)` | **E1**: mid band + trim-init 0.2 (goal-state exposure; ONE change vs xw26) — inflight-hold discriminator proved the hold skill is missing | **BIGGEST SINGLE-CHANGE MID GAIN: 4.09 / median 3.44 / yaw 14.5°** (was 6.33/4.44/52°); hold 3.27 from trim → hold quality is the whole residual |
| 59 | [59_composite_system.md](59_composite_system.md) | `eval_composite.py` | **COMPOSITE**: 4 band champions routed by commanded speed — first envelope-wide number | **pooled 0–34 m/s: median 1.33 [1.11–1.71], 43%<1, 0 crashes** (bands 0.49 / 0.74 / 1.81 / 3.77) |
| 33 | [33_xw27_budget_ladder.md](33_xw27_budget_ladder.md) | `results_velyaw_xw27c/d` | **K4a auto-ladder** on xw27b: +8M stages while median improves >7% | 20M: 2.61 → 28M: 1.72 → 36M: **median 1.29** (−25%, still climbing) → 44M running |
| 32 | [32_xw32_att_cmd.md](32_xw32_att_cmd.md) | `results_velyaw_xw32(b)` | **ATT-CMD**: attitude-setpoint interface (structural trim stabilization) + trim-init | ★ CLOSED @36M: **ROBUST median 0.92 [0.85–1.04], 53%<1 — first sub-1 band** (44M stage flat → self-stopped); tail arm queued for the ≥85% bar |
| 31 | [31_xw31_precision_reshape.md](31_xw31_precision_reshape.md) | `results_velyaw_xw31(b)` | **ARM B**: precision weight 0.7→1.5 (incentive hypothesis; vs xw27) | **FLAT: 3.67 med** ≈ xw27 — incentive refuted |
| 30 | [30_xw30_priv_critic.md](30_xw30_priv_critic.md) | `results_velyaw_xw30(b)` | **ARM A / E6**: privileged critic (advantage-noise hypothesis; vs xw27) | **FAILURE: 5.13 med** (regression) — advantage noise refuted |
| 29 | [29_xw29_highband_trim_init.md](29_xw29_highband_trim_init.md) | `results_velyaw_xw29(b)` | HIGH anchor + trim-init 0.2 | **BEST HIGH EVER: 7.38 / median 5.88** @8s (prior 8.62 med @20s); hold 6.29 from trim → same hold deficit as mid |
| 28 | [28_xw28_trim_init_04.md](28_xw28_trim_init_04.md) | `results_velyaw_xw28(b)` | **E1 dose**: trim-init 0.4 | **FLAT: 4.64 / median 3.38** ≈ xw27 → exposure saturated; learnability impeded → arms 30/31 |
| 26 | [26_xw26_midband_proven_recipe.md](26_xw26_midband_proven_recipe.md) | `results_velyaw_xw26(b)` | **ANCHOR**: mid band, xw18b proven recipe VERBATIM (band is the only change) | **FAILURE: 6.33 / median 4.44 / 0%<1** @8s, UNIFORM across wind bins (not a tail); yaw 52° at γ0.99 → yaw collapse RE-ATTRIBUTED to the attitude gate at wing-borne bands, NOT γ |
| 20 | [20_xw21_no_aero_dr.md](20_xw21_no_aero_dr.md) | `results_velyaw_xw21(b)` | **ABLATION (user)**: aero DR OFF, high band | **11.40** — WORSE than with DR (8.94): identification REFUTED as the bottleneck; DR even regularizes |
| 19 | [19_xw20_stiff_inner_loop.md](19_xw20_stiff_inner_loop.md) | `results_velyaw_xw20(b)` | **LOOP iter 12**: stiff inner loop (kp 40/ki 10), high band | **8.94** — ripple real (~1 m/s) but not dominant; identification term now prime suspect → LSTM decides |
| 16 | [16_xw18b_floor.md](16_xw18b_floor.md) | `results_velyaw_xw18b` | **LOOP iter 10**: converge the specialist | **MILESTONE**: hover 0.78 ✓; low-band 1.89 mean / **0.82 median**, 59% of eps < 1 under FULL spec — floor = wind tail, not training |
| 54 | [54_xw54_high_refined_trim.md](54_xw54_high_refined_trim.md) | `results_velyaw_xw54` | FRESH 18–25 + refined trim-init (dose 0.3) | **FAILURE: 5.07 median @12M** vs the transfer champion's 2.03 — decisive negative about **LINEAGE**: transfer reached 2.39 in ONE 6M continuation |
| 55 | [55_xw55_vhigh_ladder.md](55_xw55_vhigh_ladder.md) | `results_velyaw_xw55a` | VHIGH 25–34 budget ladder (trained 21–34) | **3.77 band median** — the vhigh champion; earlier "flyability gate failed" verdicts at 21–34/21–35 were **undertraining, not infeasibility** |
| 56 | [56_xw56_split_integral.md](56_xw56_split_integral.md) | `results_velyaw_xw56` | split integral leak (yaw τ decoupled), fresh 18–25 | **INCONCLUSIVE by my design error** — launched on a fresh lineage immediately after trial 54 closed fresh training; rerun as trial 61 |
| 57 | [57_xw57_champion_refined.md](57_xw57_champion_refined.md) | `results_velyaw_xw57` | champion + refined (per-episode) trim-init | **FAILURE: 2.50** vs 2.03 — with trials 54 + 28, **trim-init is fully exhausted** at 18–25 |
| 58 | [58_xw58_envelope_climb.md](58_xw58_envelope_climb.md) | `results_velyaw_xw58` | envelope climb 24→37 m/s toward the 45 goal | stage a top band (33–37) median **6.95**, under the 7.0 coverage gate — climb stalled; **34–45 m/s remains uncovered** |
| 61 | [61_xw61_champion_split_integral.md](61_xw61_champion_split_integral.md) | `results_velyaw_xw61` | split integral on the CHAMPION (proper rerun of 56) | **FAILURE: 3.09 → 2.72 [CI 2.25–3.07]** vs 2.03, CIs disjoint after 16M of re-adaptation — the **true-integrator question is CLOSED** |
| 62 | [62_xw62_vhigh_precision.md](62_xw62_vhigh_precision.md) | `results_velyaw_xw62` | precision stack transferred to 25–34 | superseded by the step-matched rerun (trial 63) |
| 63 | [63_xw63_vhigh_precision_matched.md](63_xw63_vhigh_precision_matched.md) | `results_velyaw_xw63` | same, step-matched vs xw55a | **FAILURE: 5.06 [CI 4.28–6.45]** vs 3.77 — narrowing the span to 25–34 degrades the band |
| 64 | [64_xw64_high_pure_ladder.md](64_xw64_high_pure_ladder.md) | `results_velyaw_xw64` | patient low-LR ladder at 18–25 | **NULL: 2.10** vs 2.03 — the band is **not step-size limited**; ladder self-stopped after one stage |
| 65 | [65_xw65_scaffold_width.md](65_xw65_scaffold_width.md) | `results_velyaw_xw65` | scaffold width rule at 18–25 (train 14–25) | **FAILURE: 2.48 [CI 2.08–2.88]** vs 2.03 — the width rule does **NOT** transfer down |
| 66 | [66_xw66_scaffold_width_vhigh.md](66_xw66_scaffold_width_vhigh.md) | `results_velyaw_xw66` | scaffold width at 25–34 (train 20–34) | **FAILURE: 5.06 [CI 4.25–6.02]** vs 3.77 — width rule refuted in **both** directions; the champion's edge is **LINEAGE**, and further training at fast bands always hurt |
| 67 | [67_xw67_trim_feedforward.md](67_xw67_trim_feedforward.md) | `rate_vel_aviary.py` (`trim_ff`) | trim feedforward (residual-style assist) | **CANCELLED BY USER** — *"i don't need trim. i need only pure RL."* Code implemented but left default **OFF** |
| 68 | [68_xw68_trim_ff_deployable.md](68_xw68_trim_ff_deployable.md) | — | deployable (wind-estimate) trim FF | **CANCELLED** before any verdict — same decision |
| 69 | [69_xw69_recovery_curriculum.md](69_xw69_recovery_curriculum.md) | `results_velyaw_xw69_010/020`, `recovery_switch.py` | **RECOVERY**: failure-state dose ladder, then a supervisory switch | dose is weak and costly (recovery 12→22%, precision 0.82→**0.97**); **routing wins: pooled recovery 22% [17–28] → 46% [CI 40–53]**, post-upset median error 38.8→9.8, engaging on 4% of flights and **net positive on precision** (paired same-seed: 21.18→15.36 mean on engaged episodes, 7.4:1 benefit:harm). Detector recalibrated after firing on 47% of normal flights; "no precision cost" was a median-only artifact, corrected |
| 70 | [70_reward_scale_invariance.md](70_reward_scale_invariance.md) | `rate_vel_aviary.py` (`rel_approach`) | **ROOT CAUSE of the wide-range failure**: reward has absolute widths, so shaped gradient at rest falls 1.3e-1 (5 m/s) → **3.9e-22 (50 m/s)**, and the surviving linear pull is scaled `0.4/MAX_SPEED` so widening the envelope weakens it 5×. Explains trim-init's gain, fresh-band failure, fast-band degradation, and trial 31's null. Scale-invariant approach basin + speed-keyed linear pull implemented (absolute GOAL terms untouched) | **ANALYSIS + CODE ONLY — NOT TRAINED** (user directive: no new training) |

## Conventions
- Physical eval = `eval_velyaw.py`: 120 episodes, level start, steady-state error over the
  final 3 s. Bands: hover(0–1), low(1–10), mid(10–18), high(18–25) m/s.
- **Benchmark wind: 0–20 m/s through trial 10; 0–15 m/s (the real spec, user-confirmed) from
  trial 11 on.** S=C=b=1 confirmed as the real reference dims (trial 11).
- Dive-recovery test = `analyze_velyaw.py`: 60 episodes ALL starting in failure states
  (tough init); "recovered" = final-2 s velocity error < 8 m/s, "partial" = 8–15 m/s.
- Training curves live in [figs/](figs/) (copied from each run's `training_curve.png`).
- **Reward scales are NOT comparable across runs 04+** (the yaw gate changed the scale).
- Automation: new runs are chained as `train → analyze_velyaw → log_trial.py`, which appends
  the results section to the trial's MD automatically. The narrative sections (what/why/code)
  are written when the run is launched.

## Prior projects (documented elsewhere)
- Heavy-quad velocity + position tasks: [../docs/TRAINING_HISTORY.md](../docs/TRAINING_HISTORY.md)
- Tailsitter VTOL 0–80 m/s velocity tracking (integrator/tanh/memory study):
  [../docs/TAILSITTER.md](../docs/TAILSITTER.md)
- General lessons: [../docs/LESSONS.md](../docs/LESSONS.md)

## Directional-objective spec (user decision, 2026-08-03)
Yaw is commanded and scored at **hover/low speed only**; in fast flight the nose follows
the velocity vector and yaw is free (the attitude gate implements exactly this). Yaw
columns for mid/high/vhigh/top rows are informational. The deep-research report's
course-aware heading redesign is NOT adopted — unnecessary under this spec.

## Convention reminder (enforced 2026-08-04)
Every trial MD carries an **## Exact code changes** section with the edited code verbatim
(marked NEW/CHANGED per file), or an explicit "no code changes — flags only" pointing at
the trial where that feature's code lives. Trials 31–55 were backfilled after the
autonomous phase let this slip.
