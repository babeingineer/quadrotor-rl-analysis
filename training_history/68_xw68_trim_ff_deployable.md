# Trial 68 — xw68: trim feedforward with the DEPLOYABLE wind estimate

## Why
Trial 67 indexes the feedforward trim with the true wind — a privileged ceiling test that
measures what the architecture can do at best. This repeats it with `--trim-ff-est-wind`,
which builds the same reference from the observer's wind estimate instead: the version that
could actually fly on hardware. The gap between the two runs is the price of not knowing the
wind exactly, measured rather than assumed.

## Exact code changes
None beyond trial 67. The flag flips `trim_ff_true_wind` to False, which routes
`_solve_ff_trim()` through `_wind_vel_estimate()` — both quoted verbatim in trial 67's
section. Everything else (deviation semantics, rescan fallback, gains, recipe) is identical,
so the comparison isolates the wind source.

## Command
Trial 67's command plus `--trim-ff-est-wind`, out-dir `results_velyaw_xw68`.

## Pre-registered (vs trial 67's result R)
- **CHEAP**: within 0.3 m/s of R -> the estimator is good enough; this becomes the
  deliverable policy for the band and the composite roster updates to it.
- **MODERATE**: 0.3–1.0 m/s worse -> usable, but the estimator is now the bottleneck worth
  engineering (a proper wind-velocity observer rather than the pitot-differencing stand-in).
- **COSTLY**: >1.0 m/s worse than R -> the architecture is not deployable as built. Note
  trial 41 (airflow-observability null) already showed the *policy* cannot compensate for
  missing airflow information on its own, so this would be an estimator problem, not a
  training problem.

## Result — n/a (cancelled before any verdict)
*(auto-appended)*
