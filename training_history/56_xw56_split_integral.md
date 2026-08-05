# Trial 56 — xw56: long velocity integral + protected yaw integral (split leak)

## Why (user question: "why don't we use the true integrator?")
The classical controller's precision comes from a TRUE integrator, and the campaign tested
that idea three times — each time it failed, but the record shows WHY, and the reason was
an implementation coupling, not the idea:

| trial | setting | velocity result | yaw result |
|---|---|---|---|
| 22 | τ=1e6 bundled with γ0.999 + 20 s + stiff gains (low band) | 2.08 med (regressed) | 53° |
| 25 | τ=1e6 + 20 s ONLY, γ0.99 (low band) | **0.93 ≈ 0.88 baseline (neutral)** | **90° (destroyed)** |
| 44 | τ=10 (high band) | 5.98 vs 4.67 (worse) | — |

`rate_vel_aviary.py` used ONE leak constant for both integrals (lines 663/668), so every
test also made the YAW integral long-memory. Under this project's spec the heading error is
*unsatisfiable by design* in wing-borne flight (nose follows the velocity vector), so a
long-memory yaw integral accumulates a one-way error and pins at its ±π clamp — a
saturated, information-free, actively misleading input. Trial 25's split signature
(velocity neutral, yaw destroyed) is exactly that.

Measured after the fix (6 s, zero action, seed 7, high band):
`yaw_integral -0.22` with the protected leak vs `-0.51` and climbing with the shared leak.

Secondary caution recorded from the same smoke: the velocity integral rails at its ±25/axis
clamp during bad behaviour (‖I‖ 43.3 = 25·√3 after 6 s of zero action). The classical
baseline needed a *tight* clamp (int_clamp 8 best; 20/40/80 gave 11.4/25.0/38.4 — trial 21
addendum 4), so this run uses τ=30 rather than 1e6: long relative to an 8 s episode, but
still self-clearing. Clamp tuning is the follow-up if this arm shows signal.

## What (vs xw54's recipe: ONE change — the integral leak pair)
`--integral-tau 30 --yaw-integral-tau 3` on the high-band recipe (att-cmd, trim-init 0.3,
katt 3, fin-assist 2, stiff gains), fresh 8M + 4M @1e-4 + robust-gated ladder.

## Exact code changes
```python
# rate_vel_aviary.py — constructor arg (NEW):
                 yaw_integral_tau=None,            # separate leak for the yaw integral
                 #                                   (None = same as integral_tau)

# rate_vel_aviary.py — __init__ (NEW):
        self.INTEGRAL_TAU = float(integral_tau)
        # separate leak for the YAW integral: at speed the heading error is unsatisfiable by
        # design (nose follows the velocity vector), so a long-memory yaw integral rails at
        # +-pi and becomes a saturated, misleading input. None -> share INTEGRAL_TAU (legacy).
        self.YAW_INTEGRAL_TAU = float(integral_tau if yaw_integral_tau is None
                                      else yaw_integral_tau)

# rate_vel_aviary.py — yaw integral update (CHANGED: INTEGRAL_TAU -> YAW_INTEGRAL_TAU):
            self.yaw_integral += (dpsi - self.yaw_integral / self.YAW_INTEGRAL_TAU) * self.CTRL_TIMESTEP
            self.yaw_integral = float(np.clip(self.yaw_integral, -np.pi, np.pi))

# train.py — flag (NEW):
    ap.add_argument("--yaw-integral-tau", type=float, default=None,
                    help="separate leak for the YAW integral (default: same as "
                         "--integral-tau); keep this short when using a long velocity "
                         "integral, since heading error is unsatisfiable at speed")
# config key "yaw_integral_tau"; eval_velyaw.py / continue_train.py pass through with
#     yaw_integral_tau=cfg.get("yaw_integral_tau", None)
```
Default behaviour is unchanged for every existing config (None → shares `integral_tau`).

## Pre-registered criteria (vs the high-band champion xw51b, 2.03; and vs xw54 same-recipe)
- **SUCCESS**: median <1.7 with yaw ≤ 25° → the coupling was the blocker; adopt the split
  everywhere and retest a true (τ=1e6) velocity integral with a tighter clamp.
- **NULL**: ≈2.0 → a long velocity integral genuinely adds nothing for RL (the policy
  already receives the disturbance-observer estimate, which carries the same information
  without windup); the classical/RL difference is *use* vs *observation*, closed for good.
- **FAILURE**: >2.3 or yaw >40° → long velocity memory is harmful on its own; revert to τ=3.

## Result
*(auto-appended)*

## VERDICT: INCONCLUSIVE by my design error — rerun as trial 61
Fresh 18–25 with the split integral: **6.01 median @12M**. That cannot be compared to the
champion's 2.03, because trial 54 had just established that FRESH training at this band is
a dead end regardless of mechanism (fresh baseline with refined trim-init: 5.07 @12M).
Launching this arm fresh instead of on the champion lineage was my error; the fresh-vs-fresh
read is "no better than baseline" (6.01 vs 5.07, roughly within seed spread ±0.5–1.0).
Ladder killed at stage b to free the chain.

The mechanism itself is untested on a policy that is already precise — which is exactly
where a steady-offset remedy should show. Redone properly in
[61_xw61_champion_split_integral.md](61_xw61_champion_split_integral.md).

# continue_train.py — flags ADDED so the leak pair can change on a continuation:
```python
    ap.add_argument("--integral-tau-override", type=float, default=None,
                    help="change the velocity-integral leak for this continuation (obs "
                         "DYNAMICS change: values shift meaning, so expect re-adaptation)")
    ap.add_argument("--yaw-integral-tau-override", type=float, default=None,
                    help="change the yaw-integral leak for this continuation")

    if args.integral_tau_override is not None:
        cfg["integral_tau"] = args.integral_tau_override
    if args.yaw_integral_tau_override is not None:
        cfg["yaw_integral_tau"] = args.yaw_integral_tau_override
```
