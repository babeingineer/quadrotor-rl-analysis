# Trial 71 — audit: checkpoint integrity and the wide-range reward test

**STATUS: ANALYSIS ONLY. NO TRAINING.**

**Follow-up:** trial 72 found and fixed an additional one-stage-stale continuation-override bug
that is more consequential than the checkpoint issue alone. Read
[72_training_integrity_fixes.md](72_training_integrity_fixes.md) before using this audit to plan
another run.

This entry records two important findings discovered while reviewing the complete training
history for the 0–45 m/s goal. They change how the high-speed results should be interpreted and
what must be fixed before testing trial 70's scale-invariant reward.

## Finding 1 — staircase stages did not propagate the best checkpoint

`eval_velyaw.load()` evaluates `best/best_model.zip` when it exists, but loads the single
top-level `vecnormalize.pkl`. That normalization file is continually overwritten during
training and saved again at the final timestep. The evaluated artifact is therefore usually:

```
best PPO weights + final VecNormalize statistics
```

Those files are not a checkpoint pair.

`continue_train.py` has a different default: it loads the source run's
`ppo_ratevel_final.zip` together with its final `vecnormalize.pkl`. All inspected staircase
scripts used that default; none passed `--model-file .../best/best_model.zip`. Thus each new
stage inherited the final policy, not the policy reported as the source run's champion.

### Evidence from the key high-speed runs

The recorded `evaluations.npz` curves and model metadata show:

| run | best-policy step | final-policy step | final mean eval return / best |
|---|---:|---:|---:|
| xw55a | 108,713,208 | 114,125,088 | 0.56 |
| xw58b | 123,136,824 | 130,148,640 | 0.45 |
| xw60a | 131,148,600 | 138,160,416 | 0.52 |

The best and final ZIP hashes differ in every inspected champion run. The return ratios are
training-evaluation returns, not physical velocity-error ratios; they establish substantial
within-stage policy drift but do not quantify the physical loss by themselves.

### Corrected interpretation

The record supports:

> Continuing from the propagated **final** fast-band checkpoints repeatedly failed or regressed.

It does **not** establish:

> Continuing from each stage's reproducible best checkpoint, paired with its contemporaneous
> normalization state, also fails.

That branch was never tested. Therefore the statements in trials 62–66 that *any* further
fast-band training hurts need this checkpoint-selection caveat. The reward defect in trial 70
remains real, but checkpoint propagation is an independent confound in the envelope staircase.

## Finding 2 — trial 70's rest-start premise describes evaluation, not training

Trial 70 motivates the reward analysis with an episode starting at rest, so initial velocity
error equals commanded speed. This is true for the standard level-start evaluation. Training,
however, constructs the environment with `randomize_init=True`; ordinary training resets sample
an initial velocity magnitude uniformly from 0 to `MAX_SPEED` in a random 3-D direction.
Twenty percent of the standing fast-band recipe is then replaced by trim initialization.

Consequences:

1. Large-error gradient starvation is still real and is often worse than the rest-start table,
   because initial and target velocity vectors can oppose one another.
2. The new relative basin is scaled by **commanded speed**, not actual initial error. For a slow
   command paired with a large randomized initial velocity, the basin can itself be negligible.
3. The `rel_approach` flag changes two mechanisms together: it adds the relative Gaussian basin
   and re-keys the linear pull from `MAX_SPEED` to commanded speed. A successful run cannot
   identify which mechanism caused the gain.

### Numerical audit under the actual reset distribution

A 1,000,000-sample calculation reproduced the reset distributions at `MAX_SPEED=45`, including
the 0.2 trim-init fraction. It evaluated the magnitude of the analytical velocity-reward
gradient at reset (`vel_precision=0.7`, `cov_width=5`, `rel_width=0.5`, `rel_floor=8`):

| command band | median initial error | legacy median gradient | combined fix | ratio |
|---|---:|---:|---:|---:|
| 0–1 | 16.8 | 0.0113 | 0.0526 | 4.6× |
| 1–10 | 17.6 | 0.0103 | 0.0510 | 5.0× |
| 10–18 | 20.6 | 0.0091 | 0.0386 | 4.3× |
| 18–25 | 24.9 | 0.0089 | 0.0336 | 3.8× |
| 25–34 | 31.2 | 0.0089 | 0.0291 | 3.3× |
| 34–45 | 39.9 | 0.0089 | 0.0233 | 2.6× |

The combined trial-70 change therefore remains promising. In the low and mid bands, however,
the basin's median gradient is effectively zero under randomized starts; most of the gain there
comes from the re-keyed linear pull. This strengthens the case for a controlled ablation.

## Required corrections before another training campaign

1. Save an atomic best-checkpoint bundle: PPO weights, `VecNormalize`, config, timestep, and
   hashes from the same evaluation event.
2. Make evaluation accept explicit model and normalization paths and reject mismatched pairs by
   default.
3. Make continuation choose `--source-checkpoint best|final` explicitly and record the source
   timestep/hash in the destination config.
4. Split trial 70 into independent switches:
   - command-keyed linear pull only;
   - relative approach basin only;
   - both;
   - legacy control.
5. Select the one-policy checkpoint using per-band physical metrics (especially the worst band),
   not only mean episode return, which can hide regression in part of the envelope.

## Pre-registered next experiment

After the integrity fixes, run a matched fresh-policy screen over 0–45 m/s. Keep the established
recipe fixed (attitude-command interface, yaw gates, absolute precision 0.7, coverage width 5,
wind 0–15, full aero DR, integral leak 3 s, 50 Hz, gamma 0.99, eight-second episodes, trim-init
0.2). Compare legacy, linear-only, basin-only, and combined reward arms on identical training and
held-out evaluation seeds.

Promotion requires a clear improvement in both 25–34 and 34–45 m/s, zero crashes, and no more
than about 30% regression below 25 m/s. The winning result must reproduce across at least three
training seeds before a long budget ladder is authorized.

## Documentation rule adopted

From this entry onward, every material experiment, discovery, correction, or verdict must be
written to a Markdown file in `training_history/` and linked from `INDEX.md`. Code-only changes
that affect training or evaluation must include their rationale and exact change in that entry.
