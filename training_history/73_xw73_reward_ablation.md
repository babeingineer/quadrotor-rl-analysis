# Trial 73 — matched reward ablation for one 0–45 m/s policy

**STATUS: COMPLETE.** Ran 2026-08-05 23:10 to 2026-08-06 04:07 Asia/Taipei under supervisor
PID 23596. Arm order was legacy → linear → basin → both; all four 4M-step arms, checkpoint
selections, 600-episode balanced evaluations, nominal evaluations, and recovery tests completed.

## Why

Trial 70 found that absolute-width reward shaping is numerically negligible far from fast
commands. Trial 71 found unpaired checkpoint selection. Trial 72 found that the historical range
staircase trained one stage behind its labels and split the proposed reward repair into two
independent mechanisms. This is the first clean training test after all three corrections.

## Four matched arms

Four fresh PPO policies receive 4,000,000 steps each with seed 7300:

| arm | reward change |
|---|---|
| `legacy` | none; matched 0–45 control |
| `linear` | command-key the far-field linear pull (`--cmd-linear`) |
| `basin` | add only the command-scaled approach basin (`--rel-basin 1.0`) |
| `both` | both independent changes; equivalent to trial 70's combined proposal |

Standing recipe held fixed: 256×256 MLP PPO, attitude-command action interface, yaw gate,
attitude yaw gate, absolute precision weight 0.7, coverage width 5 m/s, wind 0–15 m/s, full
aerodynamic domain randomization, leaky integral τ=3 s, 50 Hz control, gamma 0.99, eight-second
episodes, trim-init 0.2, six environments, and entropy coefficient 0.003.

## Envelope-aware checkpoint selection

Raw SB3 “best” still maximizes mean reward and can hide a failed top band. Every 100k-step model
is now paired with its contemporaneous normalization state. After each arm, all pairs are scored
on the same held-out seeds in six bands: 0–1, 1–10, 10–18, 18–25, 25–34, and 34–45 m/s.

Selection is lexicographic:

1. fewest crashes;
2. smallest worst-band median velocity error;
3. smallest pooled median;
4. greatest pooled fraction below 1 m/s.

The selected model, normalization state, config, hashes, and full candidate audit are saved under
`envelope_best/`. Importantly, sub-band evaluation changes only target sampling; observation,
integral, and pitot normalization remain at the policy's trained 45 m/s scale. The old API could
not make that distinction because `MAX_SPEED` controlled both sampling and scaling.

Each selected arm then receives 100 held-out episodes per band (600 total), plus 120 nominal
episodes, the 60-episode upset-recovery test, and behavior traces.

## Pre-registered screening verdicts

- **PROMOTE:** linear, basin, or both clearly improves both 25–34 and 34–45 medians over the
  matched legacy arm, has zero crashes, and no below-25 band regresses by more than 30%.
- **PARTIAL:** top bands improve but a slow band regresses; next test is balanced target-band
  sampling, with reward mechanism held fixed.
- **FAIL:** no repaired arm materially improves the two fast bands; the reward defect is real but
  not binding by itself, so the next branch is control conditioning rather than more reward scale.

This 4M run is a mechanism screen, not final acceptance. A promoted arm must reproduce across
three independent seeds and then train to convergence. Final “fully working” acceptance remains:
median error below 1 m/s and at least 85% of episodes below 1 m/s in every band, zero crashes,
hover/low yaw compliance, and a separately reported upset-recovery rate.

## Exact implementation

- `run_xw73_reward_ablation.py`: sequential four-arm runner with atomic JSON status updates.
- `rate_vel_aviary.py`: independent `target_speed_max` and `set_target_speed_range()` preserve
  trained observation scaling during band-restricted evaluation.
- `select_envelope_checkpoint.py`: discovers paired periodic/best/final checkpoints, performs
  held-out minimax selection, and writes `envelope_best/selection.json` plus the selected bundle.
- `evaluate_envelope.py`: balanced 600-episode per-band measurement of the selected bundle.
- `analyze_velyaw.py`: accepts explicit model + normalization paths so recovery analysis measures
  the envelope-selected policy rather than silently returning to reward-best.
- `summarize_xw73.py`: requires every arm's selection, balanced evaluation, and recovery artifacts;
  applies the numerical promotion gates and replaces only the marked auto-results block below.

## Verification before launch

An end-to-end tiny PPO smoke produced periodic checkpoints at steps 8 and 16, paired best and
final bundles, evaluated all four candidates in all six speed bands while retaining
`MAX_SPEED=45`, selected the minimax checkpoint, wrote the audit/bundle, and completed balanced
evaluation. All edited modules compile and `git diff --check` passes.
The result synthesizer was also tested against the deliberately incomplete live run: it exited 2,
listed the missing artifacts, and left this Markdown file byte-for-byte unchanged.

## Results

Pending. Legacy arm is training. Launch validation confirmed the saved config exactly matches the
pre-registration (`max_speed=45`, legacy reward controls off, att-cmd/yaw gates/precision/DR on).
The trainer reached 24,576 steps with six live workers at approximately 1,377 fps; no startup,
environment, or logging errors were present.

Live integrity check at 258,048 steps: real training produced paired periodic checkpoints at
99,996 and 199,992 steps (one model ZIP + one normalization PKL at each), and the selector
discovered both. The atomic reward-best bundle contains model, normalization, config, and a
hash-verified manifest from exactly step 49,998. Effective throughput including 50k evaluation
rollouts and plots was approximately 815–857 fps. No traceback or supervisor failure occurred.

**500k legacy diagnostic (not a verdict):** a read-only comparison used separate seed base 37300
and only three episodes per band. The raw-reward best checkpoint at 49,998 steps had worst-band
median 36.29 m/s, pooled median 17.04, 0% below 1, and zero crashes. The paired 499,980-step
checkpoint worsened to worst-band median 66.68 and pooled median 28.66, still 0% below 1 and zero
crashes. Per-band medians changed from 5.14/6.42/16.01/21.51/32.33/36.29 to
29.07/23.79/30.12/27.87/35.23/66.68. With n=3 these values are too noisy for acceptance or early
stopping, but the direction matches trial 70's prediction that continued optimization under the
legacy wide-range reward favors the wrong behavior. The matched legacy arm continues unchanged.

**1M live milestone:** 1,007,616 steps completed with ten model/normalization checkpoint pairs,
zero pairing gaps, no traceback, and sustained effective throughput near 888–905 fps. The noisy
10-episode reward callback still selects step 49,998 (99.15 return); the last ten callback means
average −11.22 with range −58.13 to 25.64. This confirms why reward-best is not an adequate
envelope selector, but remains monitoring evidence rather than a physical verdict.

**1.5M live milestone:** 1,511,424 steps completed with 15/15 paired periodic artifacts and no
failure. Unlike the early decline, the last ten reward-callback means averaged 38.06 and a new
raw-reward best of 100.90 appeared at step 1,249,950. This reversal confirms that the full matched
budget should run; it does not overturn the 500k physical diagnostic because callback return and
worst-band physical error are different selection objectives.

**2M live milestone:** 2,002,944 steps completed with 20/20 paired artifacts and no failure.
The raw-reward best remains step 1,249,950 (100.90); the last ten callback means averaged 17.84
and ranged from −28.29 to 86.88. At the halfway point the legacy return remains highly variable,
while checkpoint integrity and throughput remain stable.

**2.5M live milestone:** 2,506,752 steps completed with 25/25 paired artifacts and no failure.
Throughput rose to roughly 954–959 fps. Raw reward reached a new best of 145.90 at step 2,199,912;
the last ten callback means averaged 42.97. This is useful evidence that PPO is optimizing the
legacy objective, but the earlier physical diagnostic shows why objective return alone cannot be
interpreted as envelope control quality.

**3M live milestone:** 3,022,848 steps completed with 30/30 paired model/normalization artifacts
and no supervisor failure. Throughput was approximately 1,012-1,024 fps. The raw-reward best
remained step 2,199,912 (mean return 145.90); the last ten callback means averaged 41.78, ranging
from -35.20 to 109.69. These noisy training-return callbacks are operational diagnostics only,
not envelope evidence.

**3.5M live milestone:** 3,514,368 steps completed with 35/35 paired periodic artifacts and no
supervisor failure. The raw-return callback found a new best of 157.80 at step 3,049,878, while
the last ten means still ranged from -41.58 to 157.80 (mean 56.14). This remains evidence of
training progress and volatility, not evidence that all target-speed bands are controlled.

**Legacy training complete:** PPO stopped at 4,005,888 vectorized steps and saved 40/40 paired
periodic artifacts plus complete final and reward-best bundles. All 80 evaluation callbacks
completed without a traceback. Raw return reached 207.35 at step 3,799,848; the last ten callback
means averaged 77.54 (range 3.58-207.35). At 2026-08-06 00:10 Asia/Taipei the supervisor moved
to held-out six-band selection across 42 complete candidates. No physical-control conclusion is
drawn from the raw return.

**Legacy selection midpoint:** after 20/42 complete candidates, every candidate had zero crashes
but 0% pooled episodes below 1 m/s. The provisional minimax leader was the 1,599,936-step pair
with 34.48 m/s worst-band and 22.03 m/s pooled median error. A different checkpoint achieved a
lower 21.10 m/s pooled median while its worst band worsened to 44.29 m/s. This directly confirms
that aggregate checkpoint scoring can conceal a severe speed-band failure; the complete ranking
continues unchanged.

**Legacy checkpoint selected:** the complete 42-candidate ranking selected the paired 2,999,880-
step checkpoint. On the 5-episode-per-band selection seeds it had zero crashes, 34.32 m/s
worst-band median, 18.02 m/s pooled median, and 0% of episodes below 1 m/s. Band medians from
hover through top were 17.36, 8.61, 10.04, 10.48, 34.32, and 31.47 m/s. The reward-best bundle
reproduced its contemporaneous periodic pair exactly, validating checkpoint pairing, but had a
worse 43.15 m/s worst-band median. The selected legacy policy plainly fails the 0-45 requirement;
its independent 100-episode-per-band evaluation is running to establish the matched control for
the reward ablation.

**Legacy arm complete:** the independent 600-episode evaluation confirmed zero crashes but 0%
of episodes below 1 m/s. Median errors for hover, low, mid, high, vhigh, and top were 11.60,
12.60, 17.11, 20.04, 25.97, and 32.48 m/s; pooled median was 19.14 m/s and worst-band median
was 32.48 m/s. A separate 120-episode nominal sample had 20.49 m/s pooled median, 0% below
1 m/s, and zero crashes. Upset recovery was only 1/60 (2%), with 29.2 m/s median final error.
The matched legacy control therefore fails decisively, including at hover and low speed, despite
its rising raw training return. The linear arm began immediately afterward; its saved config
confirms `cmd_linear=true`, `rel_basin=0`, and all other registered settings unchanged.

**Linear 500k live milestone:** 516,096 steps completed with 5/5 paired periodic artifacts, no
failure, and throughput around 1,553-1,573 fps. Its first ten callback returns averaged -146.51
(range -229.40 to 39.34), far below the legacy return scale. Because `cmd_linear` changes the
reward definition, cross-arm raw returns are not comparable and this is not evidence of worse
physical control. The arm continues to its fixed budget for held-out envelope measurement.

**Linear 1M live milestone:** 1,019,904 steps completed with 10/10 paired checkpoints, 20 finite
evaluation callbacks, no failure, and stable throughput near 1,560-1,570 fps. The last ten raw
returns averaged -188.91 (range -244.01 to -132.99), confirming numerical stability but carrying
no cross-arm performance meaning because the reward scale differs. Physical quality remains
deferred to the registered selector.

**Linear 1.5M live milestone:** 1,523,712 steps completed with 15/15 paired artifacts, 30 finite
callbacks, and no failure. The last-ten return mean improved to -141.32 from -188.91 at 1M, but
the raw-reward best still remained the 49,998-step pair. This within-arm divergence reinforces
the decision to select by held-out physical envelope metrics.

**Linear 2M live milestone:** 2,015,232 steps completed with 20/20 paired artifacts, 40 finite
callbacks, and no failure. The last-ten raw-return mean improved sharply to -55.49 (range -128.89
to 12.39), while the reward-best remained at 49,998 steps. This is within-arm evidence of ongoing
optimization, not yet evidence of improved target-speed control.

**Linear 2.5M live milestone:** 2,519,040 steps completed with 25/25 paired artifacts, 50 finite
callbacks, and no failure. The last-ten callback mean moved back to -105.16 after the halfway
improvement. This non-monotonic trajectory again supports preserving and physically scoring every
checkpoint rather than assuming later or reward-best weights are superior.

**Linear 3M live milestone:** 3,010,560 steps completed with 30/30 paired artifacts, 60 finite
callbacks, and no failure. The last-ten callback mean was -90.71 and the 49,998-step pair still
led raw reward. About one million matched steps remain before complete held-out selection.

**Linear 3.5M live milestone:** 3,502,080 steps completed with 35/35 paired artifacts, 70 finite
callbacks, and no failure. The last-ten raw-return mean improved to -61.86 on this arm's own
reward scale. Roughly 500k steps remain before held-out checkpoint selection.

**Linear training complete:** PPO stopped at 4,005,888 vectorized steps with 40/40 paired
periodic artifacts, complete best/final bundles, 80 finite callbacks, and no failure. The last-ten
raw-return mean improved to -37.91, yet reward-best still pointed to step 49,998. The supervisor
entered identical 42-candidate six-band selection at 2026-08-06 01:29 Asia/Taipei.

**Linear selection midpoint:** after 20/42 complete candidates, the 1,999,920-step pair was the
provisional minimax leader with zero crashes, 23.19 m/s worst-band median, 17.79 m/s pooled
median, and 0% below 1 m/s. Its worst-band score is about 32% lower than the legacy selector
winner's 34.32 m/s on the same small-n seed protocol, so the far-field linear term shows a real
provisional physical effect. It remains far from usable and must pass the complete ranking,
band-specific comparison, and independent 600-episode evaluation.

**Linear checkpoint selected:** the complete ranking selected the paired 3,399,864-step
checkpoint with zero crashes, 18.16 m/s worst-band median, 16.58 m/s pooled median, and 0% below
1 m/s. Selection-seed band medians were 15.21, 17.12, 13.75, 16.71, 17.43, and 18.16 m/s.
Compared with the selected legacy pair, vhigh/top improved from 34.32/31.47 by roughly 49%/42%,
but low/mid/high regressed from 8.61/10.04/10.48 by roughly 99%/37%/59%. This is provisionally
`PARTIAL`, not `PROMOTE`: command-keyed linear pull repairs fast-command learning at the cost of
slower bands. The independent 600-episode evaluation is running before that verdict is fixed.

**Linear arm complete:** on 100 independent episodes per band, median errors were 13.70, 13.79,
15.10, 17.21, 18.57, and 26.20 m/s, with 16.76 m/s pooled median, 0% below 1 m/s, and zero
crashes. Relative to legacy, vhigh improved 28.5% but top improved only 19.3%, narrowly missing
the pre-registered >=20% gate; hover/low regressed 18.1%/9.4%, while mid/high improved. The arm
is therefore `PARTIAL`, not promoted. Nominal yaw error worsened from 31.2 to 74.4 degrees median,
and upset recovery was only 2/60 (3%) with 33.4 m/s median final error. The far-field pull is
directionally useful but neither precise nor behaviorally complete by itself. The basin-only arm
started next; its config confirms `rel_basin=1`, `cmd_linear=false`, with all other settings held.

**Basin 500k live milestone:** 516,096 steps completed with 5/5 paired artifacts, ten finite
callbacks, no failure, and throughput around 1,628-1,647 fps. Raw return averaged 61.93 and peaked
at 228.34, but this scale is not comparable with either prior arm because the reward definition
changed. The observation establishes integrity only; physical conclusions remain deferred.

**Basin 1M live milestone:** 1,019,904 steps completed with 10/10 paired artifacts, 20 finite
callbacks, and no failure. The last-ten raw-return mean was 47.08 on this arm's own scale, while
the 49,998-step bundle remained reward-best. Physical selection remains decisive.

**Basin 1.5M live milestone:** 1,511,424 steps completed with 15/15 paired artifacts, 30 finite
callbacks, and no failure. The last-ten within-arm return mean rose to 110.73 (range 70.13-171.07),
showing stable optimization under the basin reward but not yet physical envelope quality.

**Basin 2M live milestone:** 2,002,944 steps completed with 20/20 paired artifacts, 40 finite
callbacks, and no failure. The last-ten within-arm return mean was 120.44, while the 49,998-step
pair remained reward-best. The arm is stable at halfway; envelope quality is still unmeasured.

**Basin 2.5M live milestone:** 2,519,040 steps completed with 25/25 paired artifacts, 50 finite
callbacks, and no failure. A new raw-best of 254.22 appeared at step 2,249,910 and the last-ten
mean rose to 158.45. Optimization now favors a mature checkpoint, but physical quality remains
unknown until the minimax evaluation.

**Basin 3M live milestone:** 3,010,560 steps completed with 30/30 paired artifacts, 60 finite
callbacks, and no failure. The last-ten within-arm return mean increased to 176.65; the 2,249,910-
step checkpoint remained reward-best. About one million steps remain before physical selection.

**Basin 3.5M live milestone:** 3,502,080 steps completed with 35/35 paired artifacts, 70 finite
callbacks, and no failure. The last-ten within-arm return mean rose to 248.21 and a new raw-best
of 304.80 appeared at step 3,449,862. Roughly 500k steps remain before physical validation.

**Basin training complete:** PPO stopped at 4,005,888 vectorized steps with 40/40 paired
periodic artifacts, complete best/final bundles, 80 finite callbacks, and no failure. The last-ten
within-arm return mean reached 299.79 and raw-best rose to 356.20 at step 3,649,854. Identical
42-candidate held-out physical selection began at 2026-08-06 02:36 Asia/Taipei.

**Basin selection midpoint:** after 20/42 complete candidates, the 1,399,944-step pair was the
provisional minimax leader with zero crashes, 26.95 m/s worst-band median, 25.11 m/s pooled
median, and 0% below 1 m/s. Despite the arm's strong late training return, this was provisionally
worse than the selected linear pair on both envelope and pooled error. The full ranking continues.

**Basin checkpoint selected:** the complete ranking selected the paired reward-best bundle at
step 3,649,854 with zero crashes, 17.31 m/s worst-band median, 13.65 m/s pooled median, and 0%
below 1 m/s. Selection-seed band medians were 10.12, 16.68, 15.76, 7.87, 16.42, and 17.31 m/s.
Relative to legacy, vhigh/top improved about 52%/45% and high improved, but low/mid regressed
about 94%/57%. Thus basin is also provisionally `PARTIAL`: it improves fast acquisition but does
not preserve the slower envelope. Independent 600-episode evaluation is running.

**Basin arm complete — PROMOTE:** on 100 independent episodes per band, median errors were 14.12,
14.40, 12.21, 14.25, 18.10, and 18.93 m/s, with 15.22 m/s pooled median, 0.2% below 1 m/s, and
zero crashes. Relative to legacy, vhigh/top improved 30.3%/41.7%; hover/low regressed only
21.7%/14.3%, and mid/high improved. This passes every pre-registered relative promotion gate and
overturns the small selector sample's exaggerated slow-band tradeoff. Nominal yaw improved to
23.0 degrees median. Upset recovery remained poor at 3/60 (5%) with 27.7 m/s median final error.
Basin is the first mechanism worth multi-seed replication, but it is emphatically not fully
working. The combined arm started with both `rel_basin=1` and `cmd_linear=true`, all else held.

**Combined 500k live milestone:** 516,096 steps completed with 5/5 paired artifacts, ten finite
callbacks, and no failure. Raw return averaged -85.70 and peaked at 148.88 on this arm's unique
reward scale. This establishes run integrity only; comparative performance remains unmeasured.

**Combined 1M live milestone:** 1,019,904 steps completed with 10/10 paired artifacts, 20 finite
callbacks, and no failure. The last-ten within-arm return mean was -130.50 and the 49,998-step
bundle remained reward-best. Physical selection remains decisive.

**Combined 1.5M live milestone:** 1,511,424 steps completed with 15/15 paired artifacts, 30
finite callbacks, and no failure. The last-ten within-arm return mean improved modestly to
-110.61, while the early 49,998-step bundle remained reward-best.

**Combined 2M live milestone:** 2,002,944 steps completed with 20/20 paired artifacts, 40 finite
callbacks, and no failure. The last-ten within-arm return mean improved sharply to -33.25 (range
-88.39 to 70.54), although the 49,998-step bundle remained raw-best.

**Combined 2.5M live milestone:** 2,506,752 steps completed with 25/25 paired artifacts, 50 finite
callbacks, and no failure. The last-ten within-arm return mean turned positive at 11.35 but still
ranged widely from -156.71 to 110.32; the 49,998-step bundle remained raw-best.

**Combined 3M live milestone:** 3,022,848 steps completed with 30/30 paired artifacts, 60 finite
callbacks, and no failure. The last-ten within-arm return mean was 4.71 with wide variability;
about one million steps remain before held-out selection.

**Combined 3.5M live milestone:** 3,502,080 steps completed with 35/35 paired artifacts, 70 finite
callbacks, and no failure. The last-ten within-arm return mean rose to 60.71, while the 49,998-
step bundle remained raw-best. Roughly 500k steps remain before selection.

**Combined training complete:** PPO stopped at 4,005,888 vectorized steps with 40/40 paired
periodic artifacts, complete best/final bundles, 80 finite callbacks, and no failure. Raw-best
finally moved to step 3,999,840 at 165.52; the last-ten mean was 68.26. Identical 42-candidate
held-out physical selection began at 2026-08-06 03:42 Asia/Taipei.

**Combined selection midpoint:** after 20/42 complete candidates, the 1,999,920-step pair was
the provisional minimax leader with zero crashes, 28.18 m/s worst-band median, 18.15 m/s pooled
median, and 0% below 1 m/s. It remained materially worse than either individual reward mechanism
at its selected checkpoint, providing no midpoint evidence of a beneficial interaction.

**Combined checkpoint selected:** the complete ranking selected the paired 3,599,856-step
checkpoint with zero crashes, 20.14 m/s worst-band median, 15.26 m/s pooled median, and 0% below
1 m/s. Selection-seed band medians were 13.55, 14.97, 12.62, 15.36, 20.14, and 17.09 m/s.
It did not beat basin overall and provisionally regressed legacy low/high beyond the 30% gate.
The independent 600-episode evaluation is running before the interaction verdict is fixed.

**Combined arm complete — PARTIAL:** on 100 independent episodes per band, median errors were
15.12, 16.94, 14.29, 16.17, 18.01, and 22.14 m/s, with 16.87 m/s pooled median, 0% below 1 m/s,
and zero crashes. Vhigh/top improved 30.7%/31.8% over legacy, but low regressed 34.4%, failing
the below-25 gate. Nominal yaw was poor at 71.3 degrees median. Recovery was only 2/60 (3%),
despite a somewhat lower 24.1 m/s median final error. Adding linear pull to basin is therefore
inferior to basin alone and is not the mechanism to replicate.

<!-- AUTO_RESULTS_START -->

**Automated screening verdict: PROMOTE `basin` to three-seed replication.**

Balanced held-out evaluation: 100 episodes per band, selected by the independent checkpoint-selection seed set.

| arm | selected checkpoint | hover | low | mid | high | vhigh | top | worst | crashes | recovery |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| legacy | periodic-2999880 @2,999,880 | 11.60 / 0% | 12.60 / 0% | 17.11 / 0% | 20.04 / 0% | 25.97 / 0% | 32.48 / 0% | 32.48 | 0 | 2% (29.2 m/s med) |
| linear | periodic-3399864 @3,399,864 | 13.70 / 0% | 13.79 / 0% | 15.10 / 0% | 17.21 / 0% | 18.57 / 0% | 26.20 / 0% | 26.20 | 0 | 3% (33.4 m/s med) |
| basin | reward-best @3,649,854 | 14.12 / 0% | 14.40 / 0% | 12.21 / 1% | 14.25 / 0% | 18.10 / 0% | 18.93 / 0% | 18.93 | 0 | 5% (27.7 m/s med) |
| both | periodic-3599856 @3,599,856 | 15.12 / 0% | 16.94 / 0% | 14.29 / 0% | 16.17 / 0% | 18.01 / 0% | 22.14 / 0% | 22.14 | 0 | 3% (24.1 m/s med) |

Fast-band comparison against legacy:

| arm | vhigh improvement | top improvement | worst <25 ratio | gate |
|---|---:|---:|---:|---|
| linear | 28.5% | 19.3% | 1.18× | **PARTIAL** |
| basin | 30.3% | 41.7% | 1.22× | **PROMOTE** |
| both | 30.7% | 31.8% | 1.34× | **PARTIAL** |

This is a one-seed, 4M-step mechanism screen. Even a PROMOTE verdict is not final task success; it authorizes three-seed replication and convergence training.

<!-- AUTO_RESULTS_END -->
