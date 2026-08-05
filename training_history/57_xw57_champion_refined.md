# Trial 57 — xw57: champion lineage + refined trim-init (high band)

## Why
xw51's polish stages ran BEFORE the per-episode trim refinement existed (implemented
2026-08-04 03:10; xw51 ran 22:50–06:49 the night before). Continuing the champion now picks
up refined goal states for free — its config already has `trim_init: 0.2`. Trial 54 showed
the refinement can't be judged from a fresh lineage (fresh-vs-transfer dominates: 5.07 vs
2.03), so this is the clean test on the lineage that matters.

## What (vs xw51b: ONE effective change — refined vs table trim-init)
`continue_train.py --src results_velyaw_xw51b --extra 8000000 --lr 1e-4 --wind-oversample 0.5`,
robust-gated stages (>7% median improvement), max 4.

## Exact code changes
None for this trial — the refinement code is in trial 56's section (`_refine_trim`), and it
activates for any run whose config has `trim_init > 0`. Commands only.

## Pre-registered (vs xw51b 2.03, 23% <1)
- SUCCESS: median <1.7 → refinement is the lever at speed; carry it into the 21–34 ladder.
- PROGRESS: 1.7–1.9 → keep laddering.
- FAILURE: ≥1.9 → refinement adds nothing at this band; high-band precision rests on
  xw56 (split integral) and, failing that, the trim-feedforward architecture.

## Result
*(auto-appended)*

---

## AUTO-CAPTURED RESULTS (2026-08-04 16:22)

**config**: `{"max_speed": 25.0, "speed_min": 18.0, "wind_max": 15.0, "use_integral": true, "use_yaw_integral": true, "use_wind_est": true, "yaw_width": 0.35, "yaw_weight": 1.0, "yaw_bias": 0.3, "heading_frame": false, "xwing_aero": true, "tough_init": 0.0, "wind_curriculum": false, "yaw_gate": true, "yaw_gate_floor": 0.2, "vel_precision": 0.7, "trim_init": 0.2, "priv_critic": false, "att_cmd": true, "katt": 1.5, "yaw_att_gate": true, "cov_width": 5.0, "kp_rate": "25,25,15", "ki_rate": "6,6,3", "aero_dr": true, "integral_tau": 3.0, "ent_coef": 0.003, "gamma": 0.99, "episode_len": 8.0, "wind_oversample": 0.5}`

**eval curve**: n=160, first 628, best 876 @ 89,084,196, last 579 (final steps 90,084,156)

**late trend**: plateaued (last-10% mean 548 vs prior-10% 549)


![training curve](figs/velyaw_xw57a_curve.png)


### Physical eval
```
=== PHYSICAL EVAL (level start, full wind, 8s episodes) ===

band           n    mean  median   %<1     p90     yaw
--------------------------------------------------------
high(18-25)  100    6.41    2.26   30%   19.20   22.4°
--------------------------------------------------------
ALL          100    6.41    2.26   30%   19.20   22.4°   crash 0.0%
wind bins: [0-5) n=23 med 1.74 <1: 30%  [5-10) n=42 med 1.57 <1: 38%  [10-15) n=35 med 2.79 <1: 20%
```


### Dive-recovery test
```
=== DIVE-RECOVERY TEST (60 episodes, all starting in failure states) ===
  recovered (final-2s vel err < 8 m/s):  8/60 = 13%
  partial   (8-15 m/s):                  0/60 = 0%
  median final err: 35.1 m/s   mean: 36.1 m/s
```


### Behavior traces
```
--- trace seed 1005: target [19.8  8.7  0.4] (|v|=21.6), wind [ -3.6 -11.6  -3.1] ---
  t= 0.0 |v|=  0.1 vz=   0.0 tilt=   0 verr= 21.7 yawerr=+103.5 fins=( -6.0,-10.5) thr=+0.56
  t= 2.0 |v|= 15.1 vz=   1.2 tilt=  55 verr=  6.7 yawerr= +31.5 fins=(+18.5,-20.0) thr=-0.89
  t= 4.0 |v|= 17.8 vz=  -0.4 tilt=  61 verr=  4.1 yawerr=  +1.9 fins=(+18.5, +6.5) thr=-1.00
  t= 6.0 |v|= 18.0 vz=   0.3 tilt=  68 verr=  3.8 yawerr= +15.8 fins=(+18.5, +0.0) thr=-0.60
--- trace seed 1012: target [  8.1 -21.4   1.8] (|v|=23.0), wind [-0.3  4.1 -6.1] ---
  t= 0.0 |v|=  0.0 vz=   0.0 tilt=   0 verr= 23.0 yawerr= +46.7 fins=( +9.6, -8.9) thr=+1.00
  t= 2.0 |v|= 20.8 vz=   2.1 tilt=  57 verr=  2.4 yawerr=  +8.2 fins=( -3.6,-18.2) thr=-0.25
  t= 4.0 |v|= 22.1 vz=   1.3 tilt=  56 verr=  1.1 yawerr=  +0.1 fins=(-11.9,-18.2) thr=-0.22
  t= 6.0 |v|= 21.9 vz=   0.8 tilt=  57 verr=  1.5 yawerr=  +2.7 fins=(-11.5,-18.2) thr=-0.22
--- trace seed 1020: target [-14.7  16.5   1.4] (|v|=22.1), wind [-0.3 -1.2 -0.6] ---
  t= 0.0 |v|=  0.0 vz=   0.0 tilt=   0 verr= 22.1 yawerr= -65.7 fins=(+10.6,+10.9) thr=+0.06
  t= 2.0 |v|= 15.1 vz=   1.1 tilt=  69 verr=  7.1 yawerr= +15.8 fins=( +0.4,-20.0) thr=+0.18
  t= 4.0 |v|= 19.6 vz=   2.1 tilt=  47 verr=  3.0 yawerr=  +7.6 fins=(+20.0,-20.0) thr=-1.00
  t= 6.0 |v|= 19.4 vz=   2.6 tilt=  48 verr=  3.1 yawerr=  -0.3 fins=(+19.3,-20.0) thr=-1.00
```

## VERDICT: FAILURE — 2.50 vs the champion's 2.03 (pct 23, unchanged). Refined trim-init
adds nothing at 18–25; the ladder self-stopped after one stage. Combined with trial 54
(fresh + refinement = 5.07) and trial 28 (dose 0.2→0.4 flat at mid), **trim-init is fully
characterised: the mechanism is worth its first 20% dose and nothing beyond it — not more
dose, not better trim quality.** The high band's champion remains xw51b (2.03).
Remaining untried mechanisms for 18–25: xw56's split integral (running next), then the
trim-feedforward architecture (needs the user's full-RL-purity call).

---

## AUTO-CAPTURED RESULTS (2026-08-04 16:29)

**config**: `{"max_speed": 25.0, "speed_min": 18.0, "wind_max": 15.0, "use_integral": true, "use_yaw_integral": true, "use_wind_est": true, "yaw_width": 0.35, "yaw_weight": 1.0, "yaw_bias": 0.3, "heading_frame": false, "xwing_aero": true, "tough_init": 0.0, "wind_curriculum": false, "yaw_gate": true, "yaw_gate_floor": 0.2, "vel_precision": 0.7, "trim_init": 0.2, "priv_critic": false, "att_cmd": true, "katt": 1.5, "yaw_att_gate": true, "cov_width": 5.0, "kp_rate": "25,25,15", "ki_rate": "6,6,3", "aero_dr": true, "integral_tau": 3.0, "ent_coef": 0.003, "gamma": 0.99, "episode_len": 8.0, "wind_oversample": 0.5}`

**eval curve**: n=160, first 771, best 861 @ 81,072,420, last 574 (final steps 82,072,380)

**late trend**: DECLINING (last-10% mean 549 vs prior-10% 564)


![training curve](figs/velyaw_xw51b_curve.png)


### Physical eval
```
=== PHYSICAL EVAL (level start, full wind, 8s episodes) ===

band           n    mean  median   %<1     p90     yaw
--------------------------------------------------------
high(18-25)  100    5.07    1.77   25%   14.23   17.4°
--------------------------------------------------------
ALL          100    5.07    1.77   25%   14.23   17.4°   crash 0.0%
wind bins: [0-5) n=23 med 1.36 <1: 30%  [5-10) n=42 med 1.70 <1: 29%  [10-15) n=35 med 2.90 <1: 17%
```


### Dive-recovery test
```
=== DIVE-RECOVERY TEST (60 episodes, all starting in failure states) ===
  recovered (final-2s vel err < 8 m/s):  6/60 = 10%
  partial   (8-15 m/s):                  3/60 = 5%
  median final err: 33.3 m/s   mean: 34.6 m/s
```


### Behavior traces
```
--- trace seed 1005: target [19.8  8.7  0.4] (|v|=21.6), wind [ -3.6 -11.6  -3.1] ---
  t= 0.0 |v|=  0.1 vz=   0.0 tilt=   0 verr= 21.7 yawerr=+103.5 fins=( -1.1,-10.5) thr=+0.77
  t= 2.0 |v|= 16.4 vz=   1.1 tilt=  52 verr=  5.8 yawerr= +24.2 fins=(+18.5, -2.6) thr=-1.00
  t= 4.0 |v|= 18.8 vz=  -0.8 tilt=  61 verr=  3.2 yawerr=  -2.3 fins=(+18.5,+20.0) thr=-1.00
  t= 6.0 |v|= 18.6 vz=   1.1 tilt=  71 verr=  3.1 yawerr= +15.8 fins=(+18.5,+13.1) thr=-1.00
--- trace seed 1012: target [  8.1 -21.4   1.8] (|v|=23.0), wind [-0.3  4.1 -6.1] ---
  t= 0.0 |v|=  0.0 vz=   0.0 tilt=   0 verr= 23.0 yawerr= +46.7 fins=(+10.1, -8.9) thr=+1.00
  t= 2.0 |v|= 20.7 vz=   1.9 tilt=  60 verr=  2.4 yawerr=  +2.5 fins=(-20.0,-18.2) thr=-0.32
  t= 4.0 |v|= 22.0 vz=   1.2 tilt=  57 verr=  1.2 yawerr=  -4.5 fins=(-11.5,-18.2) thr=-0.35
  t= 6.0 |v|= 22.1 vz=   0.4 tilt=  58 verr=  1.7 yawerr=  +1.3 fins=(-12.3,-18.2) thr=-0.22
--- trace seed 1020: target [-14.7  16.5   1.4] (|v|=22.1), wind [-0.3 -1.2 -0.6] ---
  t= 0.0 |v|=  0.0 vz=   0.0 tilt=   0 verr= 22.1 yawerr= -65.7 fins=(+10.6, +9.7) thr=-0.78
  t= 2.0 |v|= 14.0 vz=   1.5 tilt=  69 verr=  8.3 yawerr= +18.9 fins=( +0.4,-20.0) thr=+0.13
  t= 4.0 |v|= 19.2 vz=   1.7 tilt=  51 verr=  3.1 yawerr=  -2.0 fins=(+20.0,-20.0) thr=-0.81
  t= 6.0 |v|= 19.8 vz=   2.9 tilt=  52 verr=  2.9 yawerr=  -5.3 fins=(+14.4,-20.0) thr=-0.86
```
