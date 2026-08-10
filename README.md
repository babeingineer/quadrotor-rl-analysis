# RL Tailsitter Velocity Control (velyaw)

Full-RL velocity + heading control for a tailsitter VTOL (14 kg, 4×110 N motors, ±20°
elevons, ported XWing aerodynamic model) in PyBullet, built on
[gym-pybullet-drones](https://github.com/utiasDSL/gym-pybullet-drones).

**Task:** track a random 3-D target velocity (goal envelope 0–50 m/s) AND a commanded
heading, under per-episode wind (0–15 m/s) and ±20% domain randomization of aero
coefficients, mass, motor lag, and servo gain. The policy (PPO, MLP 256×256) commands
collective thrust + elevons + an attitude/rate setpoint; a PID inner loop runs at 500 Hz.

## Current results

Two systems exist. The **single policy** (trial 80) is the deliverable the goal asks for — one
network, one training lineage, no router. The **composite** (trials 59/69) is the older
four-specialist system, kept because it is still the most precise thing on the range it covers.

### Single policy — `results_velyaw_xw80_h` (64M steps, one lineage)
`python eval_velyaw.py --dir results_velyaw_xw80_h --episodes 300`

| band | median vel err | %<1 m/s | yaw |
|---|---|---|---|
| hover 0–1 | **0.41** | 83% | 2.1° |
| low 1–10 | **0.56** | 81% | 6.8° |
| mid 10–18 | 1.25 | 36% | 10.8° |
| high 18–25 | 2.28 | 15% | 17.0° |
| vhigh 25–35 | 5.58 | 1% | 25.0° |
| top 35–45 | 9.79 | 1% | 38.9° |
| **pooled 0–50** | **2.97** [2.54–3.77] | **25%** | 0 crashes |

### Single policy vs the four-specialist composite, on the composite's own range
The composite has no policy above 34 m/s, so 0–34 is the only fair comparison:

| system | 0–34 median | %<1 | flies 35–50? | deploys as |
|---|---|---|---|---|
| composite (4 specialists + router) | 1.22 [1.04–1.60] | 44% | no | 5 nets + routing + recovery switch |
| **single policy (xw80_h)** | **1.51** [1.28–1.63] | 37% | **yes** | 1 net |

CIs overlap. One network essentially matches four specialists plus a router on their own ground,
covers a band none of them can fly, and costs less in total (64M steps vs 36M+ each).

### How it was built (all three ingredients were necessary)
1. **Scale-invariant approach reward** (`--rel-basin`, trial 73): absolute reward widths go
   numerically dead far from a fast target — the shaped gradient at an episode's start falls from
   1.3e-1 at 5 m/s to **3.9e-22 at 50 m/s**. The basin's width tracks the commanded speed while
   every goal term stays absolute.
2. **Command-scaled observation** (`--rel-obs`, trial 79): obs divided by `MAX_SPEED` leaves a
   0.5 m/s hover error at 0.01, and VecNormalize's running std is dominated by fast-band errors.
   Adding `vel_err / max(|target|, 8)` took hover from 2.01 to 0.74 and 0% to 67% under 1 m/s.
3. **Speed curriculum in one lineage** (trial 80): `0-18 → 0-25 → 0-34 → 0-45 → 0-50`, then
   convergence at full envelope. Flat 0–50 training plateaued at 4.04; the curriculum reached
   2.97 with 25% <1. Widening the envelope costs precision monotonically — measured within one
   lineage as 1.77 → 2.78 → 3.57 → 3.85.

### Honest limits

- **The <1 m/s goal is NOT met.** The single policy clears it by median only at hover (0.41) and
  low (0.56); mid 1.25, high 2.28, vhigh 5.58, top 9.79 do not. No band reaches the
  85%-of-episodes bar, though hover (83%) and low (81%) sit at its edge. The goal envelope moved
  0–25 → 0–45 → 0–50 m/s during the campaign; these numbers are against the widest.
- **The fast bands are the whole remaining gap**, and the lineage plateaued there: convergence
  stages went 3.07 → 3.22 → 2.97 with overlapping CIs. More stages of the same recipe will not
  close it; a new mechanism is needed.
- **Descents are the specific unfixed weakness.** On the single policy, descents cost 9.55 vs
  climbs 2.87 (3.3×), with a +15.9 m/s vertical undershoot at γ=−40. Steep descents at 35–50 m/s
  need 93–105° of tilt while the action space caps commanded tilt at 80° — a measured mismatch
  whose consequence is **untested**: one attempt to lift the cap failed for an unrelated reason
  (trial 78, resolution loss) and the corrected attempt (trial 81) was stopped before any result.
- **Single seed everywhere in trials 77–81.** The %<1 improvements are large enough to trust
  directionally; individual median differences of ~10% are not.
- **Precision and coverage trade off**, now measured inside one lineage: 1.77 (0–25) → 2.78
  (0–34) → 3.57 (0–45) → 3.85 (0–50).
- **The composite is still more precise on 0–34** (1.22 vs 1.51, 44% vs 37% <1), so the single
  policy is the better *system* (one net, wider coverage) but not the more accurate one there.
- **Trial 74's three-seed replication of the basin reward is incomplete** — one fresh seed
  finished, one never ran. Do not cite the basin mechanism as replicated.
- **A known bug affects trial 69's detector description**: `recovery_switch.expected_tilt`
  compared radians to degrees and always returned the ±40° trim column. Fixed 2026-08-08, but the
  recovery-switch numbers have not been re-derived under the fix — they are self-consistent
  (calibration and scoring used the same function) but the "trim-relative" framing is unverified.
- Recovery is measured from synthetic failure-state starts in simulation; no hardware, and no
  sim-to-real transfer is claimed.

## Key findings (details in [training_history/](training_history/INDEX.md))

- **Trim feasibility proven everywhere, to 60 m/s**: exact force-balance trims exist for 100% of
  target/wind/DR draws — every residual is controller quality, not physics. The solver clips
  elevator to ±20° and thrust to 440 N *before* scoring the residual
  ([build_trim_table.py:31](build_trim_table.py#L31)), so its ~1e-10 residuals are actuator-feasible;
  stored deflections beyond 20° are unclipped optimizer coordinates in a flat direction, not
  infeasible trims. (An earlier note in this project claimed 60 m/s "needs −21° elevator, so it
  isn't flyable" — that was wrong for exactly this reason.) Level flight at 50 m/s needs 134 N of
  the 440 N available.
- **The reward goes numerically dead far from a fast target** (trial 70, analysis only): all
  velocity reward terms have absolute widths, so the shaped gradient at an episode's start falls
  from 1.3e-1 at 5 m/s to **3.9e-22 at 50 m/s**, and the one surviving term is scaled
  `0.4/MAX_SPEED` — asking for a wider envelope weakens it. This governs the far-field
  **approach** and retro-explains why trim-init helped most at speed and why fresh fast-band runs
  failed. Tested in **trial 73** (four matched 4M arms on one 0–45 policy): the scale-invariant
  `basin` arm was promoted — worst-band median 18.93 vs legacy 32.48 — but **all arms scored 0%
  of episodes below 1 m/s**, so the mechanism is real and far from sufficient. Its three-seed
  replication (trial 74) is **incomplete**: one fresh seed finished, one never ran.
- **The fast-band residual is a DESCENT asymmetry, not a speed limit** (trial 75, analysis only).
  At matched speed, descents cost 1.3× (low) to **4.2× (25–34 m/s)** more error than climbs,
  replicated across all four bands — and since targets are sampled uniformly on the sphere, half
  of every band's commands are descents. It is a **stabilization** failure: started *in* a
  commanded descent the policy departs from it (6.83×). Eliminated along the way: physics
  (per-draw trim infeasible ~0%), thrust floor (bites only at γ≤−30), required trim tilt (2.08×
  spread at constant tilt), and settling time (20 s episodes give a *wider* gap).
- **Goal-state initialization (trim-init)**: starting a fraction of training episodes at
  the target velocity in near-trim attitude was the single biggest gain at speed.
- **Attitude-setpoint action space**: the wing-borne trim is dynamically unstable; letting
  an inner attitude-P loop stabilize it structurally (policy commands setpoints) beats
  raw body-rate commands by a wide margin.
- **Robustness is a state-coverage property, not a curriculum knob.** Band specialists recover
  from upsets far worse than a full-envelope generalist, and the generalist never trained on
  failure states at all (`tough_init=0`) — breadth of experience is the whole mechanism.
  Reintroducing failure-state training moved recovery 12% → 22% but walked precision 0.82 →
  0.97, onto the goal line. Routing upsets to the generalist instead nearly doubles pooled
  recovery (22% → 46%) and is **net positive on precision too** (paired: 21.18 → 15.36 mean on
  the 4% of flights it engages, improvements outweighing regressions 7.4:1).
- **Detectors must be calibrated against data, per band.** An upset detector hand-tuned on one
  band fired in 47% of *normal* flights across the roster: a tailsitter's cruise is
  near-horizontal (nominal tilt p95 reaches 110°), so an absolute tilt limit flags ordinary fast
  flight, and these policies routinely exceed a 2.5 rad/s body-rate limit. Comparing tilt to
  the *trim attitude the command implies*, plus dwell, cut spurious firing 16× to 3%.
- **Negative results that matter**: LSTM ≪ MLP; privileged critic, reward sharpening,
  bigger nets, and removing domain randomization all failed controlled tests. Also refuted with
  measurements: 100 Hz control (retested fairly after a hyperparameter confound), PID-teacher
  distillation, airflow observability, integral memory (×3), and band splitting.

## Quickstart

```bash
pip install -r requirements.txt
pip install gym-pybullet-drones

python build_trim_table.py        # one-time: trim table for trim-init / analysis (~1 min)

# train a mid-band specialist (attitude interface + trim-init)
python train.py --xwing-aero --yaw-bias 0.3 --max-speed 18 --speed-min 10 --wind-max 15 \
    --yaw-gate --yaw-att-gate --vel-precision 0.7 --cov-width 5 --ent-coef 0.003 \
    --trim-init 0.2 --att-cmd --timesteps 8000000 --out-dir results_velyaw_run1

python continue_train.py --src results_velyaw_run1 --out results_velyaw_run1b \
    --extra 4000000 --lr 1e-4                       # convergence stage (essential)

# UNTRAINED (trial 70): single policy over the full range needs a scale-invariant approach
# reward, or the objective is numerically dead at speed. Legacy is unchanged at rel-approach 0.
# python train.py --xwing-aero --speed-min 0 --max-speed 50 --rel-approach 1.0 ...

python analyze_velyaw.py --dir results_velyaw_run1b # physical eval + recovery + traces

# THE DELIVERABLE: one policy over 0-50 m/s (trial 80 recipe, curriculum in one lineage)
python train.py --xwing-aero --yaw-bias 0.3 --speed-min 0 --max-speed 18 --wind-max 15     --yaw-gate --yaw-att-gate --vel-precision 0.7 --cov-width 5 --ent-coef 0.003     --trim-init 0.2 --att-cmd --rel-basin 1.0 --rel-obs     --timesteps 8000000 --out-dir run_a
# then continue with a growing envelope: 25 -> 34 -> 45 -> 50, +8M each at lr 1e-4,
# resuming from the previous stage's worst-band `envelope_best` bundle once it exists:
python continue_train.py --src run_a --out run_b --extra 8000000 --lr 1e-4     --max-speed-override 25 --source-checkpoint final
python select_envelope_checkpoint.py --dir run_b --episodes-per-band 6   # only valid at >=45
# finally converge at the full envelope for several more +8M stages.

# the older composite system: route by commanded speed, generalist armed for upset recovery
python eval_composite.py --episodes 400 --upsets 60 --recovery
```

## Repository map

| path | contents |
|---|---|
| `rate_vel_aviary.py` | the environment (obs/action/reward, DR, inner PID, trim-init) |
| `aero_xwing.py` | ported XWing aerodynamic model (byte-faithful) |
| `train.py` / `continue_train.py` / `train_lstm.py` | training entry points |
| `eval_velyaw.py` / `analyze_velyaw.py` / `eval_inflight.py` | evaluation (distribution metrics, dive-recovery, hold-from-trim diagnostic) |
| `eval_composite.py` | the OLDER composite system: band routing + optional recovery mode (superseded as the deliverable by the single policy, trial 80) |
| `recovery_switch.py` / `eval_recovery_switch.py` | supervisory upset-recovery switch (routing rule over two trained nets) |
| `calib_upset.py` / `diag_upset_terms.py` | detector threshold calibration and per-term false-fire attribution |
| `classical_baseline.py` | hand-tuned cascade used as a diagnostic ceiling probe |
| `priv_policy.py` | asymmetric actor-critic policy (critic-only privileged obs) |
| `build_trim_table.py` | offline trim solver (speed × path-angle grid) |
| `training_history/` | one MD per training run: change, config, results, verdict — plus [INDEX](training_history/INDEX.md), [JOURNEY](training_history/JOURNEY.md), [ELIMINATED](training_history/ELIMINATED.md) (all refuted mechanisms, with numbers), [ULTIMATE_PLAN](training_history/ULTIMATE_PLAN.md) |
| `docs/` | prior-project logs — heavy quadrotor and the 0–80 m/s tailsitter study ([SUMMARY](docs/SUMMARY.md), [TAILSITTER](docs/TAILSITTER.md), [LESSONS](docs/LESSONS.md)) — and figures |
| `legacy/` | superseded entry points kept for reference |
