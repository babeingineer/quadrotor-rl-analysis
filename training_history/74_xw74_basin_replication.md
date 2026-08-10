# Trial 74 — three-seed replication of the relative-basin mechanism

**STATUS: RUNNING.** Launched 2026-08-06 04:10 Asia/Taipei under supervisor PID 38628. Trial 73
seed 7300 passed the relative promotion gate but did not meet any operational acceptance
criterion. This trial adds fresh seeds 7401 and 7402, producing three independent training seeds
in total. Seed 7401 trains first; seed 7402 is queued.

## Why

Trial 73's basin-only arm reduced the 25–34 and 34–45 m/s median errors by 30.3% and 41.7%
relative to its matched legacy arm, with zero crashes and no below-25 band regression above 30%.
Its absolute performance was still poor: 15.22 m/s pooled median, 18.93 m/s worst-band median,
0.2% of episodes below 1 m/s, and 5% upset recovery. A single seed cannot distinguish a robust
mechanism from a favorable initialization.

## Registered experiment

- Existing promoted seed: 7300 from `results_velyaw_xw73_basin`.
- Fresh replication seeds: 7401 and 7402.
- Each fresh policy receives 4,000,000 steps with the exact Trial 73 basin configuration:
  0–45 m/s targets, relative basin 1.0, command-linear off, wind 0–15 m/s, full aerodynamic
  randomization, attitude-command interface, yaw gates, trim-init 0.2, and six environments.
- Each seed preserves paired policy/normalization checkpoints every 100k steps. All 42 candidates
  are selected on seed base 17300 with five episodes per band.
- Each selected pair receives 100 independent episodes per band on seed base 27300, plus nominal
  and upset-recovery tests.
- Trial 73 and Trial 74 intentionally reuse evaluation seeds so policy-seed variability is measured
  against the same episode population.

## Replication gate

The basin mechanism replicates only if both fresh seeds independently pass the Trial 73 relative
gate against the same legacy baseline: zero crashes; at least 20% improvement in both vhigh and
top median; and no hover/low/mid/high median above 1.30× legacy. Absolute 0–45 acceptance remains
median below 1 m/s and at least 85% below 1 m/s in every band, plus yaw and recovery checks.

## Exact implementation

`run_xw74_basin_replication.py` is a non-overwriting sequential runner for seeds 7401 and 7402.
It uses the same train → paired minimax selection → balanced evaluation → recovery sequence as
Trial 73, writes atomic state to `xw74_status.json`, and keeps fixed selection/evaluation seeds.
`summarize_xw74.py` requires all three complete seed records, applies the relative gate per seed,
and updates only the marked result block. Its incomplete-run test exited 2, identified the missing
artifacts, created no summary, and left this document byte-for-byte unchanged.

## Results

Launch validation found the expected basin-only config, six live training workers, and 12,288
completed steps for seed 7401. No startup, environment, or logging error was present.

**Seed 7401 500k live milestone:** the audit observed 565,248 steps, 5/5 expected paired periodic
artifacts, 11 finite callbacks, no failure, and throughput around 1,613-1,622 fps. A new within-
seed raw-best of 125.47 appeared at step 299,988, but replication quality remains deferred to
physical selection.

**Seed 7401 1M live milestone:** 1,007,616 steps completed with 10/10 paired artifacts, 20 finite
callbacks, and no failure. The last-ten within-seed return mean was 23.29 and the 299,988-step
pair remained raw-best.

**Seed 7401 1.5M live milestone:** 1,511,424 steps completed with 15/15 paired artifacts, 30
finite callbacks, and no failure. The last-ten within-seed return mean rose to 110.74 and a mature
raw-best of 154.90 appeared at step 1,299,948, resembling seed 7300's mid-training improvement.

**Seed 7401 2M live milestone:** 2,015,232 steps completed with 20/20 paired artifacts, 40 finite
callbacks, and no failure. The last-ten within-seed return mean rose to 181.38 and a new raw-best
of 253.58 appeared at step 1,949,922. Optimization is strong and mature, pending physical proof.

**Seed 7401 2.5M live milestone:** 2,506,752 steps completed with 25/25 paired artifacts, 50
finite callbacks, and no failure. The last-ten within-seed return mean remained strongly positive
at 166.86; the 1,949,922-step pair remained raw-best.

**Seed 7401 3M live milestone:** 3,010,560 steps completed with 30/30 paired artifacts, 60 finite
callbacks, and no failure. The last-ten within-seed return mean rose to 227.33 and a new raw-best
of 332.97 appeared at step 2,549,898. Basin learning is strongly reproduced at the objective
level; the physical gate remains pending.

**Seed 7401 3.5M live milestone:** 3,502,080 steps completed with 35/35 paired artifacts, 70
finite callbacks, and no failure. The last-ten within-seed return mean remained strong at 190.49,
while the 2,549,898-step pair remained raw-best. Roughly 500k steps remain.

**Seed 7401 training complete:** PPO stopped at 4,005,888 vectorized steps with 40/40 paired
periodic artifacts, complete best/final bundles, 80 finite callbacks, and no failure. Raw-best
moved to the final periodic checkpoint at step 3,999,840 with return 351.96; the last-ten mean
was 258.38. Identical 42-candidate physical selection is underway.

**Seed 7401 selection midpoint:** after 20/42 complete candidates, the 1,599,936-step pair was
the provisional minimax leader with zero crashes, 19.25 m/s worst-band median, 16.28 m/s pooled
median, and 0% below 1 m/s. This is close to seed 7300's 18.93 m/s high-confidence worst band and
is promising small-sample replication evidence, not yet a gate result.

<!-- AUTO_RESULTS_START -->

Pending completion of both fresh seeds.

<!-- AUTO_RESULTS_END -->
