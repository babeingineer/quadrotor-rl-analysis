# Trial 81 — resolution-preserving tilt extension (STARTED, STOPPED, NO VERDICT)

**STATUS: ABANDONED MID-STAGE-A by user directive** (2026-08-10: *"if current trainign finiished,
just document everything and don't start training more"*). Reached 47.85M of a 53.83M stage-a
target (~2M of 8M new steps) before being stopped. **No result. Do not cite any number from this
trial.** The design and its rationale are recorded so it can be resumed exactly as specified.

## Why it was queued
xw80_h (trial 80) is the best single 0–50 policy — pooled 2.97, 25% <1, and on 0–34 it matches
the four-specialist composite. Its one unfixed weakness is **descents**:

| | descents | climbs | ratio |
|---|---|---|---|
| xw77 (flat 0–50) | 6.14 | 3.77 | 1.63× |
| **xw80_h (curriculum)** | **9.55** | **2.87** | **3.3×** |

The curriculum improved climbs (3.77 → 2.87) and made descents worse, with the vertical
undershoot back at **+15.9 m/s at γ=−40**. The plausible cause: early curriculum stages train at
0–18 m/s where trim tilt is ~20°, teaching a low-tilt regime that does not extend. Steep descents
at 35–50 m/s need **93–105°** of tilt (measured from the trim table), and the `att_cmd` action
space caps commanded tilt at **80.0°**.

## What (one variable vs xw80_h)
`--att-tilt-ext 120`, warm-started from `results_velyaw_xw80_h` at 45.83M steps, 3 × 8M at
lr 1e-4, everything else identical.

**Why this is not trial 78 again.** Trial 78 lifted the same cap by rescaling `|xy|` linearly onto
0–120°, which halved resolution across the whole action ball and was **3.5× worse** (damage worst
at hover, 3.7×). This keeps the legacy `arcsin` mapping **exactly** for `|xy| ≤ 0.9` and spends
only the outer 10% of the ball reaching 120°:

```python
if n <= 0.9:
    tilt = float(np.arcsin(n))                       # legacy, bit-for-bit
else:
    f = min((n - 0.9) / 0.1, 1.0)
    t0 = float(np.arcsin(0.9))
    tilt = t0 + f * (np.radians(self.ATT_TILT_EXT) - t0)
self._bz_des = np.array([np.sin(tilt) * u[0], np.sin(tilt) * u[1], np.cos(tilt)])
```

Verified before launch — commanded tilt at `|xy|` = 0 / 0.3 / 0.6 / 0.9 / 0.95 / 1.0:

| mapping | 0 | 0.3 | 0.6 | 0.9 | 0.95 | 1.0 |
|---|---|---|---|---|---|---|
| legacy | 0 | 17 | 37 | 64 | 72 | **80 (cap)** |
| ext=120 | 0 | 17 | 37 | 64 | **92** | **120** |

Identical where the policy spends most of its time; reach added exactly where steep descents need
it. Because the semantics change only above `|xy| = 0.9`, a warm start from xw80_h is legitimate,
though some re-adaptation was expected (the policy commands `|xy| > 0.9` roughly a third of the
time).

## Exact code changes (NEW)
`rate_vel_aviary.py` — constructor param `att_tilt_ext: float = 0.0`, stored as
`self.ATT_TILT_EXT`, plus the decode branch above placed before the `ATT_TILT_MAX` branch and the
legacy branch. `att_tilt_ext = 0` leaves the legacy path untouched.
`train.py` — `--att-tilt-ext`, written into `config.json` and forwarded to `base_kwargs`.
`continue_train.py` — `--att-tilt-ext` CLI override (applied to `cfg` **before** `base_kwargs` is
built, per trial 72) plus `att_tilt_ext=cfg.get("att_tilt_ext", 0.0)`.
`eval_velyaw.env_kwargs` — reads the same key with a legacy-safe default.

A launch failed first because the config read was wired but the `continue_train.py` CLI flag was
not; fixed, then confirmed active (`config.json: att_tilt_ext 120.0`, `[RESUME] loaded explicit
pair from results_velyaw_xw80_h at 45,834,456 steps`).

## Pre-registration (unused — recorded for a future resume)
Baseline xw80_h: pooled 2.97 / 25% <1 on 0–50; descents 9.55 vs climbs 2.87 (3.3×); top 35–45 =
9.79; high = 2.28.
- **SUCCESS**: descent/climb ratio falls below ~2× AND top 35–45 improves, with hover/low holding
  their sub-1 medians → the tilt cap was a real binding constraint for the fast bands.
- **NULL**: descents unchanged → the cap is NOT the binding constraint for the top band; stop the
  interface line of attack entirely and record it in ELIMINATED.md.
- **FAILURE**: overall regression → warm-starting across an action-semantics change does not work;
  a fresh run would be required to test the mapping fairly.

## Honest note
Two interface attacks have now been designed off the same measurement (the 80° cap vs 93–105°
required). The first was refuted for a reason unrelated to the cap itself (resolution loss). This
second one was never run, so **the cap hypothesis remains untested**, not supported.
