# Trial 45 — xw45: band-extension transfer (mid champion → high band)

## Why
Every single-variable lever at the high band is refuted by experiment (trials 38–44:
authority, width, airflow, rate, wind-tail, integral memory, budget, settle time — the
policy holds a ~4.7 offset indefinitely). Meanwhile the mid champion holds 0.82 median.
Fresh-training the high band keeps failing; extending the WORKING policy's envelope
upward reuses its proven hold skill and skips the from-rest desert.

## What
Stage A: continue xw35b (+6M @1e-4), target range 10→21 m/s (obs-scale shift ×0.857).
Stage B: continue stage A (+8M), range 12→25 (shift ×0.84). Wind oversample kept at 0.5.

## Pre-registered
- SUCCESS: 18–21 median ≤ 2.5 at stage A with 10–18 retention ≤ 1.2 → proceed to B;
  18–25 median ≤ 3 at stage B → ladder toward <1.
- FAILURE: extension band ≥ 4 (no better than fresh xw38c) → transfer refuted; the
  remaining option is teacher–student from the classical cascade (K4b), then the honest
  capability discussion.

## ★ Stage A VERDICT: TRANSFER VALIDATED — the campaign's second breakthrough
6M continuation to 10–21: **extension band 18–21 median 1.51, 41% <1** (fresh-trained
high-band best after 20M+: 4.67, 0% <1). Retention 10–18: 0.93 (vs 0.82, acceptable).
Mechanism: the hold skill TRANSFERS upward — the high band's difficulty was discovery,
not physics. Stage B (12–25) auto-training; the staircase to 45 m/s (trial 47) armed
behind it.

## Stage B VERDICT: 12–25 → **18–25 band median 2.39, 21% <1** (fresh-training best:
4.67, 0%). Mid retention 1.02. Staircase gate passed → trial 47 stage 1 (15–30)
auto-launched. High-band polish ladder (toward <1) queued after envelope coverage.

---

## AUTO-CAPTURED RESULTS (2026-08-03 11:00)

**config**: `{"max_speed": 25.0, "speed_min": 12.0, "wind_max": 15.0, "use_integral": true, "use_yaw_integral": true, "use_wind_est": true, "yaw_width": 0.35, "yaw_weight": 1.0, "yaw_bias": 0.3, "heading_frame": false, "xwing_aero": true, "tough_init": 0.0, "wind_curriculum": false, "yaw_gate": true, "yaw_gate_floor": 0.2, "vel_precision": 0.7, "trim_init": 0.2, "priv_critic": false, "att_cmd": true, "katt": 1.5, "yaw_att_gate": true, "cov_width": 5.0, "kp_rate": "25,25,15", "ki_rate": "6,6,3", "aero_dr": true, "integral_tau": 3.0, "ent_coef": 0.003, "gamma": 0.99, "episode_len": 8.0, "wind_oversample": 0.5}`

**eval curve**: n=160, first 1023, best 1141 @ 59,199,102, last 795 (final steps 66,048,828)

**late trend**: still rising (last-10% mean 834 vs prior-10% 811)


![training curve](figs/velyaw_xw45b_curve.png)


### Physical eval
```
=== PHYSICAL EVAL (level start, full wind, 8s episodes) ===

band           n    mean  median   %<1     p90     yaw
--------------------------------------------------------
mid(10-18)    42    1.78    0.98   50%    3.32    4.7°
high(18-25)   58    4.66    2.52   22%   10.21   11.4°
--------------------------------------------------------
ALL          100    3.45    1.45   34%    8.02    8.6°   crash 0.0%
wind bins: [0-5) n=23 med 1.08 <1: 39%  [5-10) n=42 med 1.12 <1: 43%  [10-15) n=35 med 2.36 <1: 20%
```


### Dive-recovery test
```
=== DIVE-RECOVERY TEST (60 episodes, all starting in failure states) ===
  recovered (final-2s vel err < 8 m/s):  9/60 = 15%
  partial   (8-15 m/s):                  3/60 = 5%
  median final err: 36.3 m/s   mean: 34.7 m/s
```


### Behavior traces
```
--- trace seed 1005: target [17.2  7.5  0.4] (|v|=18.7), wind [ -3.6 -11.6  -3.1] ---
  t= 0.0 |v|=  0.1 vz=   0.0 tilt=   0 verr= 18.8 yawerr=+103.5 fins=( +2.9,-10.5) thr=-0.30
  t= 2.0 |v|= 13.4 vz=   1.2 tilt=  63 verr=  5.9 yawerr= +24.4 fins=(+18.5,+20.0) thr=-0.84
  t= 4.0 |v|= 15.9 vz=   1.6 tilt=  58 verr=  3.5 yawerr= +17.0 fins=(+18.5, +8.7) thr=-1.00
  t= 6.0 |v|= 14.3 vz=   0.3 tilt=  53 verr=  4.5 yawerr= +15.7 fins=(+18.5,+18.9) thr=-0.94
--- trace seed 1012: target [  7.5 -19.8   1.7] (|v|=21.3), wind [-0.3  4.1 -6.1] ---
  t= 0.0 |v|=  0.0 vz=   0.0 tilt=   0 verr= 21.3 yawerr= +46.7 fins=( +7.2, -8.9) thr=+1.00
  t= 2.0 |v|= 19.0 vz=   1.0 tilt=  56 verr=  2.5 yawerr= -12.9 fins=(-20.0,-18.2) thr=+0.01
  t= 4.0 |v|= 20.6 vz=   0.2 tilt=  55 verr=  1.8 yawerr=  +3.9 fins=(-19.2,-18.2) thr=-0.17
  t= 6.0 |v|= 20.6 vz=   0.1 tilt=  55 verr=  1.8 yawerr=  +3.7 fins=(-20.0,-18.2) thr=-0.26
--- trace seed 1020: target [-13.1  14.7   1.2] (|v|=19.7), wind [-0.3 -1.2 -0.6] ---
  t= 0.0 |v|=  0.0 vz=   0.0 tilt=   0 verr= 19.7 yawerr= -65.7 fins=(+10.6,+10.9) thr=-1.00
  t= 2.0 |v|= 15.5 vz=   0.2 tilt=  61 verr=  4.4 yawerr= +33.7 fins=(+14.1,-20.0) thr=-0.43
  t= 4.0 |v|= 17.7 vz=   1.6 tilt=  44 verr=  2.0 yawerr=  -1.2 fins=(-17.4,-20.0) thr=-0.91
  t= 6.0 |v|= 18.2 vz=   2.3 tilt=  45 verr=  2.0 yawerr=  -1.6 fins=(-17.0,-20.0) thr=-1.00
```

## Exact code changes
```python
# continue_train.py — flags (NEW; enables band-extension transfer on a continuation):
    ap.add_argument("--max-speed-override", type=float, default=None,
                    help="widen the target-speed envelope for this continuation (band-extension "
                         "transfer); obs scaling uses the same MAX_SPEED so update config too")
    ap.add_argument("--speed-min-override", type=float, default=None)

# continue_train.py — applied to the copied config before env construction (NEW):
    if args.max_speed_override is not None:
        cfg["max_speed"] = args.max_speed_override
    if args.speed_min_override is not None:
        cfg["speed_min"] = args.speed_min_override
```
Note the obs scaling: `vel_err / MAX_SPEED` and `tgt / MAX_SPEED` shift when MAX_SPEED
changes, so each extension stage also rescales the policy's inputs — bounded per stage
(x0.857 for 18->21, x0.84 for 21->25) and re-learned during the stage.
