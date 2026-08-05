# Trial 55 — xw55: proper multi-stage ladder at 21–34

## Why
Diagnosis of the staircase stalls: each new range received ONE 8M stage, while every band
that reached goal (low 0.88→0.46, mid 6.33→0.82) needed 3–5 staged continuations. The
"flyability gate failed" verdicts at 21–34/21–35 (5.97/6.19) were undertrained, not
blocked. This commits a full ladder to 21–34 with wind oversampling.

## Pre-registered (from xw53a 5.97)
- Continue while the band median improves >7%/stage (max 4 stages).
- Target: ≤3 → then extend to 24–37 with the same ladder discipline.

## Exact code changes
No code changes — flags only on the existing implementation (the feature's code is in the trial cited below).
(band-extension flags: trial 45; oversampling: trial 35.) The correction this trial
embodies is procedural — a full ladder per range instead of one stage:
```bash
SRC=results_velyaw_xw53a; PREV=5.97
for ST in a b c d; do
  OUT=results_velyaw_xw55${ST}
  "$PY" continue_train.py --src $SRC --out $OUT --extra 8000000 --n-envs 6 --lr 1e-4 \
    --max-speed-override 34 --speed-min-override 21 --wind-oversample 0.5
  # robust gate: continue while the band median improves >7%
done
```

## Stage log
- Stage a (+8M): band median 5.97 → **4.23** (−29%), top 28–34 at 5.32 — gate passed,
  stage b running. Confirms the diagnosis: the earlier "gate failed" verdicts at this
  range were undertrained, not blocked.
- Stage b (+8M): 4.28 ≈ 4.23 → **ladder self-stopped. 21–34 champion: xw55a, band median
  4.23 (top 28–34: 5.32).** The ladder bought one big stage (−29%) then saturated — the
  same shape as the high band's polish (2.40 → 2.03 → stop). Pattern across the campaign:
  each range's ladder yields ~1–2 productive stages, and the remaining gap needs a
  mechanism, not more of the same stages.

---

## AUTO-CAPTURED RESULTS (2026-08-04 15:20)

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
