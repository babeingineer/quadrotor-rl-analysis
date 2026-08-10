# Trial 72 — training-integrity fixes before the 0–45 m/s reward ablation

**STATUS: ANALYSIS + IMPLEMENTATION + SMOKE VERIFICATION. NO LONG TRAINING.**

Trial 71 identified unpaired best checkpoints. Implementing that repair exposed a more
consequential historical bug: continuation overrides were written to the destination config
*after* the environment arguments had already been constructed. The saved config and physical
evaluation used the requested new speed range, but that continuation's training environment used
the source range. TensorBoard output also retained the source model's old log directory.

This entry documents the discovery, its effect on the historical conclusions, all code changes,
and the pre-registered four-arm reward screen.

## Root cause — continuation overrides were one stage stale

The old order in `continue_train.py` was effectively:

```python
cfg = load_source_config()
base_kwargs = dict(max_speed=cfg["max_speed"], speed_min=cfg["speed_min"], ...)
if args.max_speed_override is not None:
    cfg["max_speed"] = args.max_speed_override
if args.speed_min_override is not None:
    cfg["speed_min"] = args.speed_min_override
train_env = RateVelAviary(**base_kwargs)  # still contains the source values
save_destination_config(cfg)              # contains the requested values
```

The same ordering defect affected `integral_tau_override` and
`yaw_integral_tau_override`. Wind oversampling and tough-init were applied separately when
constructing `train_kwargs`, so those two overrides were not stale.

### What this means historically

Physical evaluations remain observations of real policies under the destination config. What is
wrong is the claimed training exposure and causal attribution:

| trials | recorded intent | actual training consequence |
|---|---|---|
| 45 | extend 10–18 → 10–21 → 12–25 | each continuation trained the source range; the apparent first extension gain was zero-shot generalization |
| 47/49/50/52/53/58 | staircase to higher ranges | each changed-range stage trained one rung behind its label; its evaluation tested the new range before that range entered training |
| 51 | specialize 12–25 → 18–25 | first stage still trained 12–25; later same-range continuation trained 18–25, so the final champion remains trained on the proper range |
| 55 | repeated 21–34 ladder | stages themselves used 21–34 once the source config already carried that range; not directly stale |
| 58 → 60 | climb toward 40 | xw58 stages were one rung behind; xw60a's no-override consolidation finally trained 27–40 correctly |
| 61 | split integral, claimed 16M adaptation | stage a trained the old τ=3 dynamics but was evaluated as τ=30; stage b provided only 8M of actual τ=30 adaptation |
| 63 | narrow 21–34 → 25–34 | first/only reported stage actually trained 21–34 again; “narrowing hurts” was not tested |
| 65 | widen 18–25 → 14–25 | first/only reported stage actually trained 18–25 again; the scaffold-width verdict is invalid |
| 66 | widen 21–34 → 20–34 | first/only reported stage actually trained 21–34 again; the second scaffold-width verdict is invalid |
| 64 | 18–25 → 18–25 | bounds were unchanged, so this trial is not affected by the range-order bug |

This does not create evidence of good 40–45 m/s control. It strengthens the conclusion that the
top band is untrained: xw60a eventually trained through 40 m/s, but no verified training stage
reached 45 m/s.

## Fix 1 — overrides now precede environment construction

`continue_train.py` now applies every config mutation first, then derives `base_kwargs` from the
mutated config. It prints the effective speed bounds, both integral time constants, and episode
length before constructing an environment. The output config also records the actual episode
length and immediate source lineage.

Lineage metadata contains:

```json
{
  "source_dir": "absolute source path",
  "source_checkpoint": "best or final",
  "source_timestep": 123,
  "source_model_sha256": "...",
  "source_vecnormalize_sha256": "..."
}
```

## Fix 2 — reproducible checkpoint pairs

New `checkpoint_utils.py` provides:

- SHA-256 hashing;
- atomic `VecNormalize` saves;
- a manifest written only after the model and normalization pair exists;
- strict resolution of `best`, `final`, explicit, or historical `legacy-best` artifacts;
- hash verification when a manifest exists.

`ProgressPlotCallback` now saves the matching normalization state whenever SB3 saves a new best
model. A new best bundle contains:

```
best/best_model.zip
best/vecnormalize.pkl
best/config.json
best/checkpoint.json
```

Periodic `CheckpointCallback` calls now use `save_vecnormalize=True`. Final model and
normalization artifacts get `checkpoint_final.json`.

`continue_train.py` now requires either `--source-checkpoint best|final` or an explicit model and
normalization pair. It refuses a model without its paired normalization file. Evaluation defaults
to `auto`: paired best when available, otherwise the reproducible final pair. Reproducing an old
best-weights/final-normalization result requires the deliberately named `legacy-best` mode.

## Fix 3 — trial 70 reward mechanisms split

The historical `rel_approach > 0` behavior is preserved as a legacy combined alias. Two new,
independent controls make the causal test possible:

```text
--cmd-linear       command-key the far-field linear pull only
--rel-basin 1.0    add the command-scaled Gaussian approach basin only
```

Supplying both exactly reproduces `--rel-approach 1.0`. Mixing the legacy alias with either new
control raises an error instead of silently double-counting a term.

## Fix 4 — continuation telemetry isolation

SB3 serializes `tensorboard_log` in the model ZIP. Loading a source model retained that old path;
the smoke run visibly attempted to log into `results_velyaw_xw32/tb` despite a temporary output
directory. Continuation now resets `model.tensorboard_log` to the destination's `tb/` directory.

## Verification performed

1. `py_compile` passed for all edited Python modules; `git diff --check` passed.
2. A 24-step, same-seed XWing simulator test exercised legacy, linear-only, basin-only, explicit
   combined, and legacy-combined reward modes. Every reward was finite. Explicit combined and
   the legacy alias were bit-identical (`max delta = 0.0`). The first attempt supplied a 4-D
   action and correctly failed because the XWing/elevon environment has `ACT_DIM=6`; the rerun
   used the actual action dimension and passed.
3. A tiny PPO run forced best checkpoints at steps 4 and 12. The resolved step-12 bundle contained
   all four required files, and manifest hash verification passed.
4. A zero-step continuation smoke loaded xw55a's explicit final pair and requested speed 34–45,
   velocity-integral τ=4, yaw-integral τ=2, and nine-second episodes. Both the effective-environment
   line and saved config reported exactly those values; the lineage recorded `final`.
5. On a legacy run, `checkpoint=auto` selected the matching final pair with a warning. Strict
   `checkpoint=best` rejected the incomplete historical best bundle as designed.
6. The final zero-step continuation rerun logged into its temporary destination `tb/PPO_0`,
   produced a hashed final manifest, and repeated the exact requested 34–45/τ4/τyaw2/9 s config;
   the inherited TensorBoard-path leak is fixed.

## Pre-registered next experiment — trial 73

`run_xw73_reward_ablation.py` defines four fresh, matched 4M-step PPO screens over 0–45 m/s:

| arm | flags | question |
|---|---|---|
| legacy | none | matched wide-envelope control |
| linear | `--cmd-linear` | is the re-keyed far-field slope sufficient? |
| basin | `--rel-basin 1.0` | does the relative basin help independently? |
| both | both flags | does the combined trial-70 proposal win? |

Everything else is held fixed: seed 7300, 256×256 PPO, attitude-command interface, yaw gate,
attitude yaw gate, absolute precision 0.7, coverage width 5 m/s, wind 0–15, full aero DR,
integral τ=3 s, 50 Hz, gamma 0.99, eight-second episodes, and trim-init 0.2. Each arm receives a
600-episode nominal physical evaluation using its paired best checkpoint plus a 120-episode
recovery analysis.

The screen is prepared but not launched. Promotion still requires improvement in both 25–34 and
34–45, zero crashes, and no large regression below 25 m/s; the winner must then reproduce over
three independent training seeds.
