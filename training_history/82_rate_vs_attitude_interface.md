# Trial 82 — why rate control (CTBR) "failed", re-examined (ANALYSIS ONLY, no training)

User question (2026-08-10): *"why is it hard to use rate-controller? but it's easy when attitude
controller? i want to use rate-controller."*

## The premise is only half true — rate control OWNS the low band
From the champions' own configs:

| policy | band | interface | result |
|---|---|---|---|
| **xw48c** | 0–10 | **RATE (att_cmd=False)** | **0.44 median, 0.27 at hover — best low-speed result in the project** |
| xw17 | 0–25 | **RATE** | 5.26 (the old generalist plateau) |
| xw35b | 10–18 | attitude | 0.77 |
| xw51b | 18–25 | attitude | 1.77 |
| xw55a | 25–34 | attitude | 5.73 |
| xw80_h | 0–50 | attitude | 2.97 pooled |

Rate control is not inferior in general. It produces the most precise policy this project has at
low speed. The attitude interface was adopted at trial 32 for the *mid* band and never revisited
below it.

## Attempted mechanism: "rate cannot hold an unstable trim" — NOT SUPPORTED
Hypothesis: with CTBR the policy must close the attitude loop itself (rate integrates into
attitude), whereas `att_cmd`'s inner P-loop supplies attitude feedback structurally. Prediction:
holding trim should degrade far worse under RATE as airspeed rises.

Test (`diag_rate_vs_attitude.py`): place the aircraft exactly at table trim for level flight at V,
issue the ideal hold command for each interface (RATE: ω_des = 0; ATT: bz_des = trim thrust axis)
with identical trim thrust and elevons, no policy, no wind, no DR, and measure attitude drift
after 2 s.

**Single seed looked dramatic and was noise.** It showed 41.8° vs 1.8° at 14 m/s (22.8×). Five
seeds:

| V | RATE drift | ATT drift | ratio |
|---|---|---|---|
| 10 | 3.4° | 6.5° | 0.5× (rate better) |
| 14 | 16.8° | 9.3° | 1.8× |
| 18 | 19.5° | 15.2° | 1.3× |
| 22 | 8.4° | 18.3° | 0.5× (rate better) |

**No consistent interface advantage.** The mechanism story is refuted by its own test, and the
single-seed table should not be cited. (Process note: I published the single-seed numbers before
seeding them — the same error this campaign has now made more than once.)

## What the record actually supports
The attitude interface was introduced at trial 32 and produced the first sub-1 band (0.92
robust median vs the mid band's previous 6.33). That gain is real. But it was measured **against
a mid-band CTBR baseline from the pre-reward-fix era**, and it has never been re-tested since.

**The decisive confound: every CTBR result predates the three changes that actually moved the
single-policy campaign.** `rel_basin` (trial 73), `rel_obs` (trial 79), and the speed curriculum
(trial 80) are all **interface-independent**, and together they took a single 0–50 policy from
~5 m/s to 2.97 pooled with hover at 0.41. No CTBR policy has ever been trained with any of them.

So "CTBR 5.26 vs attitude 0.92" compares an old recipe to a new one, not one interface to another.

## How to use rate control — the clean experiment
Run the **xw80 recipe with `att_cmd` off**, changing exactly one variable from the current best:

```
python train.py --xwing-aero --yaw-bias 0.3 --speed-min 0 --max-speed 18 --wind-max 15 \
    --yaw-gate --yaw-att-gate --vel-precision 0.7 --cov-width 5 --ent-coef 0.003 \
    --trim-init 0.2 --rel-basin 1.0 --rel-obs \
    --timesteps 8000000 --out-dir results_velyaw_xw83_a          # NOTE: no --att-cmd
# then the same curriculum: 25 -> 34 -> 45 -> 50 (+8M each, lr 1e-4), then converge at 0-50.
```

Baseline to beat: xw80_h at 2.97 pooled / 25% <1, hover 0.41, low 0.56.
- **Rate wins or ties** → drop `att_cmd` entirely; CTBR is simpler and already owns the low band.
- **Rate loses at speed only** → the interface advantage is real and speed-dependent, which
  justifies the hybrid the composite already used (CTBR below ~10, attitude above).
- **Rate loses everywhere** → the trial-32 result generalises and the question is closed properly.

Two supporting levers if the first attempt disappoints, both currently untested **for CTBR**:
1. **Higher control rate.** 100 Hz was refuted (trial 39: 3.81 vs 2.38) — but that test ran with
   `att_cmd`, where the inner loop already closes the fast loop, so it had little to gain. Under
   CTBR the policy *is* the attitude loop, so the rate argument is much stronger there.
2. **Stiffer rate PID.** Trial 19 (kp 40 / ki 10) gave 8.94 and was judged "real but not
   dominant" — also pre-reward-fix, and also worth one clean retest under the modern recipe.

## Honest limits
- No training was run for this analysis; the experiment above is a proposal, not a result.
- The hold test uses no wind and no DR. `att_cmd`'s inner P-loop plausibly earns its keep as a
  disturbance rejector rather than as a trim holder, and that was not measured.
- The most likely real advantage of `att_cmd` is **learnability** (a constant action maps to a
  constant attitude, so the action→outcome mapping is simpler), which a hold test cannot probe at
  all. Testing it needs the training comparison above.
