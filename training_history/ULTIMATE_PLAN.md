# ULTIMATE PLAN — velyaw full-RL redesign (v1, 2026-07-31)

Constraint honored throughout: final system is **pure RL** (per-band RL policies switched on the *commanded* target speed is full RL — no classical control in the loop). Classical baseline is used only as a diagnostic yardstick. Per project memory: **nothing launches without explicit user instruction**; every run below is a proposal to be green-lit.

---

## 1. DIAGNOSIS — four root causes that explain the whole record

**RC1 — The campaign is grading the tail and calling it the task (measurement error).**
Every verdict is a band MEAN, but under full-spec DR/wind the error distribution is bimodal: xw18b low = mean 1.89 vs **median 0.82, 59%<1** (trial 16); classical mid = mean 4.97 vs **median 0.20, 60%<1** (trial 21 add.2); classical high = 7.55 vs 3.90. RL's mid/high **medians have never been measured**. Since the reward-free classical controller reproduces the same mid mean floor ~5, a large share of the mean is *robustness across draws* — which no reward repricing, curriculum, or budget increase touches. The "<1 m/s" mandate has never been operationally defined (open question 9). Low band plausibly already passes a median/%<1 criterion; hover passes outright (0.78).

**RC2 — Zero clean mid/high datapoints exist: every specialist verdict is contaminated.**
All 7 runs at γ≥0.997 collapsed yaw (55–83°, trials 13/14/17/19/20/22/23) and the queued rebalance was never run; trials 22/23 — the only outright regressions (0.82→2.08 median; 10.51) — were 3–4-variable bundles carrying a possibly-railed true-integrator observation (rate_vel_aviary.py:512-513, code-verified possible, never observed), 20 s dilution, stiff gains, and the γ collapse simultaneously. The record therefore contains **no fair mid or high specialist**. xw26 (xw18b recipe verbatim + only `--speed-min 10 --max-speed 18`, γ0.99, τ=3, 8 s), now mid-training, is the first — and its interim curve is *healthier* than xw17's was at the same step count, which already weighs against the desert/floor-trap theories.

**RC3 — Verdicts issued mid-climb without the one proven amplifier.**
The only sub-1 result ever (xw18b) came from the only two-stage converged lineage (8M @3e-4 + 6M @1e-4; 2.31→1.89 mean / 0.82 median). Mid/high specialists were judged single-stage at 10–15M. But scale beyond ~2x has zero in-project support and three post-saturation regressions against it (trials 05, 12, 14; xw17b physically regressed 5.26→6.24 while its eval-reward "improved"). Budget is an amplifier with a hard evidence ceiling, not a mechanism fix.

**RC4 (hypothesis tier, not foundation) — Hold-regime data scarcity.**
Training init is isotropic U(0,MAX_SPEED) uncorrelated with the target, with `_resample_target()` after state init (rate_vel_aviary.py:354-372): trim-attitude-at-target starts have P≈0, while eval grades final-3s hold. Code-verified real, but its consequence is refuted at low band (xw18b settles fine), mis-aimed at high band (xw19 *reaches* the band and fails to *hold* — tilt 25→118°), and untested at mid. It stays as a gated EXPERIMENT with a designed discriminator, not a foundation claim.

What is explicitly **not** a root cause (adversarially verified): observability (classical hits 0.20 median on policy-visible sensors; trial 20 no-DR was *worse*), capacity (trial 11), algorithm family (LESSONS §1, trial 18), physics (100% of draws have exact trims, addenda 5-6), and the yaw-gate-floor "4th trap" as a behavioral reality (arithmetic is correct — floor pays +0.14/step net at level loiter, inversion 3.8 vs 2.1/step settled — but no trace ever occupies either state; xw23b's limit cycle paid ~0 yaw at 65–172° error).

---

## 2. THE REDESIGN

### MUST (foundation — all zero-training-cost, do before any new run)

**M1. Metric surgery in `eval_velyaw.py` (~1 hour).** In `report()` print per band: n, mean, **median, %episodes<1 (steady-window), p90**, wind-bin breakdown (draw <5 / 5–10 / 10–15 m/s), and **band-conditioned yaw** (yaw scored against the 15° bar at hover/low only; reported informationally at mid/high). Add `--init {rest,inflight}`: `inflight` starts at v = target_vel + N(0,1 m/s), coarse-trim attitude, motors at trim thrust. Fixed seeds (`venv.seed(1000+i)`) make all of this retroactive.

**M2. Retroactive rescoring.** Re-run the upgraded eval on xw17 (mid/high bands), xw18b, xw20b, xw23b, and the latest xw26 checkpoint, under both `rest` and `inflight`. This single table adjudicates RC1 (is RL's mid median already low?) and RC4 (can existing policies hold from trim?) before any training.

**M3. Pre-register the success criterion with the user.** Proposal: per band, rest-start protocol, **median <1 AND ≥85% of episodes <1** in the steady window, yaw <15° where band-applicable. Also ask which mandate is operative: standstill→fast within 10 s, or in-flight hold/retarget. No big run launches until this is signed.

**M4. Zero-cost mechanism diagnostics.**
(a) Checkpoint replay: roll xw22b, xw23b, xw18b ~20 eps each logging `vel_integral`; measure fraction of steps with |I| pinned at ±MAX_SPEED. Converts the railed-integrator suspicion into observation.
(b) Physically evaluate xw17b's best-by-eval checkpoint @13.65M vs xw17@12M (tests "continuation beats parent" as physical fact vs eval-reward artifact).
(c) From saved checkpoints, log fraction of early-training episodes reaching d<5 for xw26 vs xw17 (desert discriminator: Monte Carlo predicts 14.3% vs 20% initial cov>0.1 at mid — close numbers refute the desert).
(d) Per-step reward-accounting harness (trial-03/07/11 method) ready to run on xw26 eval traces.

**M5. Code hygiene (no behavior change to running chains).**
- `continue_train.py`, after `VecNormalize.load`: `if abs(v.gamma - model.gamma) > 1e-9: v.gamma = model.gamma; v.ret_rms = RunningMeanStd(shape=())` + a printed warning. Policy stays: never change γ on resume.
- Expose `VEL_PULL` as config (default 0.02) and `--yaw-gate-floor` (default 0.2) so later single-variable trials are flags. `--yaw-weight` already exists (train.py:81) — do not re-add.

**M6. Interaction guard (adopt unconditionally).** The queued yaw_weight 3–4x is **struck for any speed-band run while yaw_gate_floor>0**: verified 1.46–1.73/step level-loiter payout, squarely in trial-03 dive-trap economics.

**M7. `eval_composite.py` (deployable-system baseline, full-RL-compliant).** Load xw18b for commanded |target|<10 and xw17@12M for 10–25 (later replaced by xw26/x-high descendants); route on target speed; report under M1 metrics. Every future specialist drops straight into a deployable artifact; expected composite ≈4.5–5 immediately.

### SHOULD (amplifiers — proven or near-proven, single-variable)

**S1. Two-stage convergence on every specialist that lands GOOD/WEAK:** `continue_train.py --src <run> --lr 1e-4`, +6–8M. The trial 15→16 precedent is the only mechanism that ever produced sub-1.

**S2. `yaw_gate_floor 0.2 → 0` at speed bands** as a single-variable cleanup — but only if xw26 traces show actual floor-harvesting (sustained windows tilt<25°, d>8, |yawerr|<20° with ≥0.4/step attributed to gated yaw). The floor is redundant since the R22 gate (trial 08); keep the R22 gate itself — do **not** replace it with a commanded-speed gate (mid-band yaw is largely satisfiable: ~4–8 N·m weathervane vs ~32 N·m motor torque; classical tracked yaw at these tilts).

**S3. First-ever clean high-band anchor:** xw18b recipe verbatim + `--speed-min 18 --max-speed 25` (γ0.99, τ=3, 8 s, default gains). No high specialist has ever run without γ-0.997 contamination.

### EXPERIMENT (uncertain — each gated, each single-variable, xw26 as controlled baseline)

**E1. Trim-init** `--trim-init-frac 0.2` (not 0.4 — bounds VecNormalize return-std inflation and transition dilution; tailsitter oversampling precedent). Gate: xw26 FAILURE **and** inflight-hold eval (M1/M2) shows the policy cannot hold from trim (inflight median >>1). Implementation: move `_resample_target()` before state init; write the Nelder-Mead trim solver (exists only as prose in trial 21 addenda) solving against the episode's **actual** DR draw + wind; nominal-keyed cache acceptable only after a one-time check that residual accels stay <0.5 m/s²; init v = target + N(0,1–2), attitude = trim ∘ U(0,10°) scatter, motors/fins at trim. Eval stays rest-start.

**E2. Speed-mix** `--speed-mix '0.3:1-10,0.7:10-18'`. Gate: xw26 FAILURE **and** desert-consistent accounting (d pinned >10, cov<0.02, no band touches — unlike xw19). VEL_PULL untouched. Note the desert is only quantitatively real at high band (3.2% vs 20% usable-gradient starts), so this is more likely to fire there.

**E3. Gamma isolation pair** (only if mid/high recipes end up needing γ0.997 horizons):
Run A — xw18b verbatim, change ONLY γ 0.99→0.997, fresh 8M. Collapse (>30° vs 4.9°) confirms γ as driver with episode length/band/integrals held fixed; clean yaw refutes it.
Run B (conditional on A collapsing) — xw17 recipe verbatim, change ONLY yaw_weight 1→**2.0–2.5** (not 3.5; caps loiter yaw pay at ~0.84–1.05/step, under the ~1-unit trap threshold). Success: yaw <15° with ALL/mid/high within 0.3 of 5.26/5.14/8.58.

**E4. Integral memory** — gated on M4(a) replay showing heavy railing (>50% steps vs <5% for xw18b) AND xw25 implicating the integrator arm. Then ONE change, not two: either τ=10 with the existing hard clip (clip engages at err≈1 m/s — adequate for a sub-1 campaign), or τ=3 with clip→`tanh(I/MAX_SPEED)` (full-scale, not 0.3·MAX_SPEED which saturates by 0.6 m/s). Fresh run (obs change). Default anchor everywhere remains τ=3.

**E5. Heading-frame anchor:** `velyaw_heading_frame=True` (already implemented, lines 552-559, never once tested) on the xw18b/xw26 recipe, fresh run. Cheap, high-information, bounded downside.

**E6. Asymmetric privileged critic** (Dict obs {'obs':40,'priv':27}; actor sees only 'obs'; deployment artifact unchanged) — always a separate FRESH trial, never a mid-lineage mutation. This is the designated weapon against the wind/DR tail if RC1's rescoring shows the tail is the real residual.

---

## 3. STAGED EXPERIMENT PLAN

Throughput basis: 58–95M steps/day realized, max 2 chains; one 8M fresh + 6M continue lineage ≈ 0.4–0.6 day/chain.

### Stage 0 — NOW (while xw26 trains; zero training cost; ~1 day)
1. **Do not touch xw26; keep xw25 queued unchanged.** They are the pre-registered isolation ladder and the cheapest bits of information in the whole plan.
2. Implement M1–M7. Run M2 rescoring and M4 diagnostics.
3. Pre-register criteria with the user (M3).
**Pre-registered pivot in Stage 0 itself:** if M2 shows xw17's mid **median** is already ≤1.5 (never measured!), the "mid is stuck" framing collapses into a tail/spec problem — Stages 1–2 re-scope to tail engineering (E6 path) and the desert/floor/speed-mix experiments are all deprioritized.
**Deliverable:** one decision table (per-band median/%<1/p90/wind-bin, rest + inflight, all checkpoints) before any launch.

### Stage 1 — Foundation validation (smallest run proving the redesign; ~0.5–1 day)
Read the xw26 verdict against its pre-registered bands, then branch:

- **GOOD (mean ≤3.5, yaw <15°):** floor-trap, inversion, desert, and hard-floor claims are all refuted at mid. Run **xw26b = continue @lr 1e-4, +6–8M** (S1) — this is the redesign's smallest proof. Success criterion (pre-registered): mid rest-start **median <1 with ≥60%<1** (85% is the Stage 2 bar). If median lands <1 → Stage 2. If median stalls ≥2 with wind-bin showing tail dominance → tail problem → E6 privileged critic fresh trial.
- **WEAK (3.5–6):** convergence stage first anyway (cheapest proven lever); re-verdict at xw26b.
- **FAILURE (>6 or yaw >30°):** run M4(d) trace accounting + the inflight discriminator, then launch exactly ONE arm on the xw18b-verbatim recipe with xw26 as controlled baseline (~0.6 day):
  - never-reaches-band, cov≈0 signature → **E2 speed-mix**;
  - cannot-hold-from-trim (inflight median >>1) → **E1 trim-init 0.2**;
  - floor-harvesting windows in accounting → **S2 floor=0**;
  - railed-integral or thrash signature resembling xw23b → wait for xw25 before acting (E4 path).
- **In parallel (second chain, when free): xw25** runs as queued. 2×2 readout: 26-good+25-good → γ/stiffness was the trials-22/23 poison, integral/20s exonerated (E4 dies); 26-good+25-bad → split xw26a (int-only) / xw26b (20s-only) as pre-registered; 26-bad → mid needs its own diagnosis per the branch above.

### Stage 2 — Scale to bands (~2–3 days, 2 chains)
1. **Mid:** take the Stage-1 winner to the pre-registered criterion via evidence-gated extension: +8M @1e-4 stages, continue only while each stage improves the **physical** band median by >7% (outside eval noise), hard cap ~40M. Kill criteria per stage: yaw >30° at any point; no median improvement over previous stage → stop, keep best-by-eval checkpoint (lesson 7).
2. **High (other chain): S3 clean anchor** (xw18b verbatim + speed-min 18, γ0.99, 8M+6M). Pre-register: GOOD = mean ≤6 AND median ≤3.9 (classical parity); KILL if mean not beating the generalist's 8.58 by 10M. On FAILURE: traces decide — desert signature (real at high band: 3.2% usable-gradient starts) → E2 speed-mix at high; reaches-but-cannot-hold (xw19 signature) → E1 trim-init at high; if the recipe clearly needs a longer horizon → run E3 (Run A, then Run B) before any γ0.997 high run, applying M6.
3. **E5 heading-frame** slots into any idle chain window as the cheap opportunistic anchor.

### Stage 3 — Convergence + merge into one deployable system (~1–2 days)
1. Retrain/finish final specialists with **±2–3 m/s band overlap** (`--speed-min 8 --max-speed 20` mid; `--speed-min 16` high; low stays xw18b-class at max-speed 10) so the switch never operates at a distribution edge.
2. **Composite controller (full RL):** route on commanded speed with hysteresis (e.g., up-switch 10.5 / down-switch 9.5 m/s; same at 18±0.5). Extend eval_composite.py with a **mid-episode retarget mode** to verify handoffs while accelerating through band boundaries (targets are currently never resampled mid-episode — if the user's mandate includes in-flight retasking, add `--retask-interval` training as a follow-on).
3. **Optional distillation** (DAgger from specialists into one 40-dim student) only if deployment demands a single net; otherwise the switched composite IS the deliverable.
4. Final acceptance: the M3 pre-registered criterion per band, 120-ep fixed-seed protocol, plus composite report and dive-recovery regression check (must not fall below xw17's 57%+23% by more than a pre-agreed margin; if it does, a small tough-init fraction or recovery-floor term is the queued repair — open question 2).

---

## 4. RISKS + KILL CRITERIA

**K1 — The redesign's central falsifier:** xw26 GOOD + xw26b convergence + wind-bin shows the residual mid gap lives entirely in the strong-wind/DR tail. Then *every* mechanism theory in the hypothesis list (floor trap, desert, speed-mix, trim-init, integral) is dead for mid, and the campaign becomes tail engineering: E6 privileged critic (fresh trial, pre-registered: %<1 must improve by ≥10 points at 12M or the arm dies) plus a spec conversation with the user (median<1 met; mean<1 means chasing the last decile of draws).

**K2 — Gamma diagnosis wrong:** E3 Run A stays clean at γ0.997 → the 7/7 collapse re-attributes (episode length or interaction); all long-horizon plans then require their own isolation before use. Cost contained: one 8M run.

**K3 — Trim solver infeasible in practice:** if per-draw trim residuals exceed 0.5 m/s² under the DR draw, E1 is dropped (do not ship approximate trims into training as if exact).

**K4 — Single-variable arms all fail at mid (xw26 FAILURE and E1/E2/S2 arms each miss their pre-registered deltas):** the honest conclusion is that from-scratch single-band full-RL at mid is not evidenced within this compute. Mandate-compliant fallback ladder: (a) one evidence-gated 40M budget ladder on the best arm (RC3's ceiling test); (b) **privileged-teacher → distilled-student (RMA-style)** — still pure RL at deployment; (c) present the user the measured trade with residual-RL documented as the excluded-by-mandate alternative. Classical numbers (mid median 0.20) remain the proof that the task, not the physics, is the obstacle.

**K5 — Ops:** OOM/restart risk is standing — keep VecNormSaveCallback + supervisor auto-resume, max 2 chains, n_envs 6, n_steps 2048 (do NOT bundle 4096 — lesson 22), no LSTM/frame-stack/SAC/bigger-nets/DR-off (all carry direct negative evidence: trials 03/11/18/20, LESSONS §1). Every run pre-registers GOOD/WEAK/FAILURE and early kills (yaw >30° by 4M; not beating the relevant generalist band value by 10M; eval declining 3M past best → stop, keep best-by-eval).

**Universal discipline (the meta-lesson the record charges for repeatedly):** one variable per trial; per-step reward accounting before believing any mechanism story; physical eval of best-by-eval checkpoints, never eval-reward; capability questions are not launch requests — every run above awaits explicit user go-ahead.

---
*Produced 2026-07-31 by a 17-agent analysis workflow (4 evidence readers over trials 00-26 + env code + prior projects + quantitative record; 5 diagnosis lenses; ranked; 6 proposals adversarially verified; synthesized). All 6 top proposals returned MIXED verdicts — the plan above keeps only their evidence-surviving parts.*

---
# SCOPE EXTENSION (2026-07-31, user directive): final goal is 0–45 m/s
The user's final goal: **velocity error <1 m/s on any physically-feasible target up to
45 m/s** ("set it perfectly on any target velocity that physics allows"). The 0–25 ladder
is an intermediate stage. Implications applied:
- **Feasibility verified**: trim scan over target 25–45 × wind 0/10/15 direct headwind
  (Va up to 60, Q·S ≈ 2200 N): **all residuals 0.000 — the entire extended envelope has
  exact trims at nominal coefficients** (small-α drag stays tens of N vs 440 N thrust).
- Band structure extended: vhigh(25-35), top(35-45) in eval_velyaw; trim_table.npz
  rebuilt to 60 m/s (old cells unchanged — safe for running trim-init chains).
- Stage 2 extends: after mid/high land, specialists for 25-35 and 35-45 (trim-init will
  matter MORE there: the approach desert grows with speed, and episodes must either start
  near trim or spend most of their 8 s accelerating).
- Stage 3 merge covers 6 bands (or distilled single net); MAX_SPEED plumbing already
  parameterized (--max-speed 45 works today).
