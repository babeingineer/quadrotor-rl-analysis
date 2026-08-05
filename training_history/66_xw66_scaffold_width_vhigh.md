# Trial 66 — xw66: scaffold-width rule at 25–34 (train 20–34, score 25–34)

## Why
Companion to trial 65. The 3.77 champion at 25–34 was trained on 21–34 as a *by-product of
the envelope climb* — never as a deliberate ladder. Trial 63 showed narrowing to 25–34 hurts
(5.06) and trial 62 showed stretching to 40 hurts (5.30). This runs the winning width as an
explicit multi-stage precision ladder: train 20–34, score strictly on 25–34.

## Exact code changes
None — band overrides (45), oversampling (35), robust gate (33), with the eval band pinned:
```python
rows = evaluate('$OUT', n=350, ep_len=8.0, speed_min=25.0, max_speed=34.0)
```

## Pre-registered (vs 3.77 on 25–34)
- SUCCESS: ≤2.5 → the width rule plus ladder discipline is the fast-band recipe; roll it
  out to 34–40 and update the composite roster.
- NULL: 3.5–4.0 → 3.77 is the honest limit at 25–34; the composite keeps xw55a.
- FAILURE: >4.0 → even the winning width degrades under further training here.

## Result
*(auto-appended)*

---

## AUTO-CAPTURED RESULTS (2026-08-05 07:21)

**config**: `{"max_speed": 34.0, "speed_min": 20.0, "wind_max": 15.0, "use_integral": true, "use_yaw_integral": true, "use_wind_est": true, "yaw_width": 0.35, "yaw_weight": 1.0, "yaw_bias": 0.3, "heading_frame": false, "xwing_aero": true, "tough_init": 0.0, "wind_curriculum": false, "yaw_gate": true, "yaw_gate_floor": 0.2, "vel_precision": 0.7, "trim_init": 0.2, "priv_critic": false, "att_cmd": true, "katt": 1.5, "yaw_att_gate": true, "cov_width": 5.0, "kp_rate": "25,25,15", "ki_rate": "6,6,3", "aero_dr": true, "integral_tau": 3.0, "ent_coef": 0.003, "gamma": 0.99, "episode_len": 8.0, "wind_oversample": 0.5}`

**eval curve**: n=160, first 421, best 693 @ 115,125,048, last 378 (final steps 122,124,768)

**late trend**: DECLINING (last-10% mean 353 vs prior-10% 373)


![training curve](figs/velyaw_xw66a_curve.png)


### Physical eval
```
=== PHYSICAL EVAL (level start, full wind, 8s episodes) ===

band           n    mean  median   %<1     p90     yaw
--------------------------------------------------------
high(18-25)   34    4.81    2.00   18%    7.29   17.9°
vhigh(25-35)  66    7.66    4.35    3%   18.91   18.8°
--------------------------------------------------------
ALL          100    6.69    3.32    8%   15.48   18.5°   crash 0.0%
wind bins: [0-5) n=23 med 2.65 <1: 13%  [5-10) n=42 med 3.08 <1: 7%  [10-15) n=35 med 4.70 <1: 6%
```


### Dive-recovery test
```
=== DIVE-RECOVERY TEST (60 episodes, all starting in failure states) ===
  recovered (final-2s vel err < 8 m/s):  12/60 = 20%
  partial   (8-15 m/s):                  4/60 = 7%
  median final err: 35.2 m/s   mean: 34.8 m/s
```


### Behavior traces
```
--- trace seed 1005: target [25.  10.9  0.5] (|v|=27.3), wind [ -3.6 -11.6  -3.1] ---
  t= 0.0 |v|=  0.1 vz=   0.0 tilt=   0 verr= 27.3 yawerr=+103.5 fins=( +9.0, -5.0) thr=+1.00
  t= 2.0 |v|= 17.5 vz=   1.8 tilt=  72 verr= 10.0 yawerr= +32.0 fins=(+18.5,+17.3) thr=-0.34
  t= 4.0 |v|= 23.3 vz=   2.0 tilt=  62 verr=  4.6 yawerr=  -8.5 fins=(+18.5,+20.0) thr=-1.00
  t= 6.0 |v|= 25.2 vz=   5.5 tilt=  58 verr=  7.7 yawerr= -24.6 fins=( -4.5,+20.0) thr=-1.00
--- trace seed 1012: target [ 10.5 -28.    2.4] (|v|=30.0), wind [-0.3  4.1 -6.1] ---
  t= 0.0 |v|=  0.0 vz=   0.0 tilt=   0 verr= 30.0 yawerr= +46.7 fins=(+10.1, -8.9) thr=+1.00
  t= 2.0 |v|= 23.4 vz=   3.0 tilt=  60 verr=  7.3 yawerr=  +6.4 fins=( -6.8,-18.2) thr=-0.36
  t= 4.0 |v|= 27.5 vz=   2.2 tilt=  61 verr=  2.9 yawerr=  +4.1 fins=(-13.3,-18.2) thr=-0.35
  t= 6.0 |v|= 27.7 vz=   1.8 tilt=  63 verr=  2.8 yawerr=  +7.2 fins=(-14.8,-18.2) thr=+0.17
--- trace seed 1020: target [-18.8  21.1   1.8] (|v|=28.3), wind [-0.3 -1.2 -0.6] ---
  t= 0.0 |v|=  0.0 vz=   0.0 tilt=   0 verr= 28.3 yawerr= -65.7 fins=(+10.6,+10.9) thr=+1.00
  t= 2.0 |v|= 24.4 vz=   3.9 tilt=  52 verr=  5.0 yawerr=  +7.6 fins=( +1.2,-20.0) thr=-1.00
  t= 4.0 |v|= 25.5 vz=   4.1 tilt=  62 verr=  4.2 yawerr=  +7.3 fins=(-17.8,-20.0) thr=-1.00
  t= 6.0 |v|= 25.8 vz=   3.6 tilt=  55 verr=  3.5 yawerr=  +5.2 fins=(-15.0,-20.0) thr=-1.00
```

## VERDICT: FAILURE — 5.06 [CI 4.25–6.02] vs 3.77, identical to trial 63's narrowed run.
Training 20–34 as a deliberate ladder reproduces the same degradation as training 25–34.
So the "width rule" is fully refuted in both directions: the 3.77 champion's advantage is
**not** reproducible by choosing a training span — it is a property of that checkpoint's
growth history (climb-through). Any further training at 25–34, at any span tried, makes it
worse.
**25–34 stands at 3.77 (xw55a). 18–25 stands at 2.03 (xw51b). Both bands are closed to
further mechanism or curriculum work within this architecture.**

---

## AUTO-CAPTURED RESULTS (2026-08-05 07:26)

**config**: `{"max_speed": 34.0, "speed_min": 21.0, "wind_max": 15.0, "use_integral": true, "use_yaw_integral": true, "use_wind_est": true, "yaw_width": 0.35, "yaw_weight": 1.0, "yaw_bias": 0.3, "heading_frame": false, "xwing_aero": true, "tough_init": 0.0, "wind_curriculum": false, "yaw_gate": true, "yaw_gate_floor": 0.2, "vel_precision": 0.7, "trim_init": 0.2, "priv_critic": false, "att_cmd": true, "katt": 1.5, "yaw_att_gate": true, "cov_width": 5.0, "kp_rate": "25,25,15", "ki_rate": "6,6,3", "aero_dr": true, "integral_tau": 3.0, "ent_coef": 0.003, "gamma": 0.99, "episode_len": 8.0, "wind_oversample": 0.5}`

**eval curve**: n=160, first 470, best 706 @ 108,713,208, last 398 (final steps 114,112,992)

**late trend**: still rising (last-10% mean 364 vs prior-10% 355)


![training curve](figs/velyaw_xw55a_curve.png)


### Physical eval
```
=== PHYSICAL EVAL (level start, full wind, 8s episodes) ===

band           n    mean  median   %<1     p90     yaw
--------------------------------------------------------
high(18-25)   30    4.91    2.81   13%    8.84   13.6°
vhigh(25-35)  70    7.80    3.75    3%   16.21   21.0°
--------------------------------------------------------
ALL          100    6.93    3.54    6%   15.25   18.8°   crash 0.0%
wind bins: [0-5) n=23 med 2.64 <1: 4%  [5-10) n=42 med 3.61 <1: 7%  [10-15) n=35 med 4.14 <1: 6%
```


### Dive-recovery test
```
=== DIVE-RECOVERY TEST (60 episodes, all starting in failure states) ===
  recovered (final-2s vel err < 8 m/s):  11/60 = 18%
  partial   (8-15 m/s):                  5/60 = 8%
  median final err: 34.4 m/s   mean: 38.4 m/s
```


### Behavior traces
```
--- trace seed 1005: target [25.4 11.1  0.5] (|v|=27.7), wind [ -3.6 -11.6  -3.1] ---
  t= 0.0 |v|=  0.1 vz=   0.0 tilt=   0 verr= 27.8 yawerr=+103.5 fins=( +2.9, -7.0) thr=+1.00
  t= 2.0 |v|= 20.3 vz=   1.1 tilt=  70 verr=  7.5 yawerr= +32.9 fins=(+18.5, -2.2) thr=-0.59
  t= 4.0 |v|= 25.6 vz=   1.8 tilt=  86 verr=  3.7 yawerr= +53.9 fins=(+18.5,-20.0) thr=-0.43
  t= 6.0 |v|= 24.5 vz=   9.4 tilt=  45 verr= 10.8 yawerr=  -7.0 fins=( +4.0,+20.0) thr=-1.00
--- trace seed 1012: target [ 10.6 -28.2   2.4] (|v|=30.3), wind [-0.3  4.1 -6.1] ---
  t= 0.0 |v|=  0.0 vz=   0.0 tilt=   0 verr= 30.3 yawerr= +46.7 fins=(+10.1, -8.9) thr=+1.00
  t= 2.0 |v|= 23.3 vz=   2.8 tilt=  62 verr=  7.6 yawerr= +22.0 fins=(-20.0,-18.2) thr=+0.51
  t= 4.0 |v|= 27.4 vz=   1.9 tilt=  61 verr=  3.2 yawerr=  +8.2 fins=( -9.5,-18.2) thr=-0.44
  t= 6.0 |v|= 27.5 vz=   1.4 tilt=  61 verr=  3.2 yawerr=  +8.8 fins=( -8.9,-18.2) thr=-0.24
--- trace seed 1020: target [-19.   21.4   1.8] (|v|=28.7), wind [-0.3 -1.2 -0.6] ---
  t= 0.0 |v|=  0.0 vz=   0.0 tilt=   0 verr= 28.7 yawerr= -65.7 fins=(+10.6,+10.9) thr=+1.00
  t= 2.0 |v|= 22.2 vz=   4.7 tilt=  61 verr=  7.8 yawerr=  -1.1 fins=(-12.0,-20.0) thr=-0.23
  t= 4.0 |v|= 25.7 vz=   5.3 tilt=  59 verr=  5.0 yawerr=  +9.4 fins=(-12.6,-20.0) thr=-1.00
  t= 6.0 |v|= 23.9 vz=   2.6 tilt=  61 verr=  4.9 yawerr=  +6.6 fins=( -0.1,-20.0) thr=-0.94
```
