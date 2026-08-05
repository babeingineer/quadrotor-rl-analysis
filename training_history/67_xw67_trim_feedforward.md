# Trial 67 — xw67: TRIM FEEDFORWARD at the high band (user-selected architecture)

## Why
Every pure-RL mechanism at 18–25 is exhausted (trials 38–66: authority, band split, airflow
obs, control rate, integral memory x3, trim-init dose/refinement x3, lineage, teacher–student,
oversampling, ladders at three LRs, curriculum width x2). Honest limit: median ~2.0.
The user chose the trim-feedforward architecture: the policy stops having to *discover* the
~70 deg cruise attitude and instead corrects around a known-good reference.

Design note — this is the corrected version of an idea that already failed once. Trial 65's
body-relative command (att_rel) failed because "hold current attitude" gives the loop no
absolute reference, so disturbances integrate freely. Anchoring the same parameterization to
the **trim** attitude restores an absolute reference while keeping the constant conditioning
at high tilt that motivated it. The earlier probe's defect is exactly what this fixes.

## What
Target and wind are constant within an episode, so the trim is solved ONCE at reset (table
lookup + Nelder-Mead refinement against the episode's own aero draw, with a rescan fallback),
and the policy's action becomes a DEVIATION from it:
- attitude: bz_des = R_trim · unit(k·a3, k·a4, 1)   (k = 0.4 -> max ~22 deg)
- thrust:   T = T_trim + a2 · 0.4 · NOMINAL_HOVER
- elevons:  fin = de_trim/FIN_MAX + 0.5 · a0,a1
- yaw rate: unchanged (a5)

so `a = 0` holds trim exactly.

**Measured before launch.** Trim residual over 25 draws spanning 18–45 m/s: median 0.000,
p90 0.035, max 1.886 m/s^2, with 2/25 poor solves. After adding the rescan fallback:
**median 0.000, p90 0.000, max 0.058, 0/25 poor.** Reset cost 0.039 s.
Zero-action flight still diverges (2.3 -> 28 m/s over 6 s) — expected, because the trim is an
*unstable* equilibrium: the feedforward supplies the reference, the policy must still
stabilise around it. That division of labour is the entire point of the architecture.

This run is the **ceiling test**: the feedforward is indexed with the TRUE wind. The
deployable variant (observer-estimated wind) is trial 68, queued behind it.

## Exact code changes
```python
# rate_vel_aviary.py — constructor args (NEW):
                 trim_ff: bool = False,            # TRIM FEEDFORWARD: the episode's trim
                 #                                   (attitude, elevator, thrust) is solved once
                 #                                   at reset and the policy commands only the
                 #                                   DEVIATION from it. a=0 holds trim, which is
                 #                                   an absolute reference (unlike att_rel).
                 trim_ff_k: float = 0.4,           # tilt deviation scale: max atan(k) ~ 22 deg
                 trim_ff_thrust: float = 0.4,      # thrust deviation span, x NOMINAL_HOVER
                 trim_ff_fin: float = 0.5,         # elevon deviation span, x FIN_MAX
                 trim_ff_true_wind: bool = True,   # index the trim with the TRUE wind
                 #                                   (privileged: ceiling test). False = use the
                 #                                   observer's wind estimate (deployable).

# rate_vel_aviary.py — __init__ (NEW):
        self.TRIM_FF = bool(trim_ff)
        self.TRIM_FF_K = float(trim_ff_k)
        self.TRIM_FF_THRUST = float(trim_ff_thrust)
        self.TRIM_FF_FIN = float(trim_ff_fin)
        self.TRIM_FF_TRUE_WIND = bool(trim_ff_true_wind)
        self._ff = None                            # (R_trim, de_trim, T_trim) or None

# rate_vel_aviary.py — end of _housekeeping (NEW):
        # TRIM FEEDFORWARD: target and wind are constant per episode, so the trim is solved
        # ONCE here (~0.04 s) and reused every step as the action's reference point.
        self._ff = self._solve_ff_trim() if self.TRIM_FF else None

# rate_vel_aviary.py — step(), action decode (NEW branch, ahead of the plain att_cmd one):
        if self.ATT_CMD and self.TRIM_FF and self._ff is not None:
            # deviation from the episode's trim: a=0 holds trim exactly (absolute reference)
            R_ff, de_ff, T_ff = self._ff
            xy = self.current_action[-3:-1]
            v = np.array([self.TRIM_FF_K * xy[0], self.TRIM_FF_K * xy[1], 1.0])
            self._bz_des = R_ff.as_matrix() @ (v / np.linalg.norm(v))
            self._yaw_rate_des = float(self.current_action[-1]) * float(self.MAX_RATE[2])
            thrust_des = float(np.clip(
                T_ff + self.current_action[2] * self.TRIM_FF_THRUST * self.NOMINAL_HOVER,
                0.0, self.MAX_TOTAL_THRUST))

# rate_vel_aviary.py — step(), elevon application (ADDED):
                if self.TRIM_FF and self._ff is not None:
                    fin_norm = np.clip(self._ff[1] / self.FIN_MAX
                                       + self.TRIM_FF_FIN * fin_norm, -1.0, 1.0)

# rate_vel_aviary.py — NEW method _solve_ff_trim():
    def _solve_ff_trim(self):
        """Trim (R, elevator, thrust) for this episode's target and wind, from the table +
        a short refinement against the actual aero draw. Returns None below ~2 m/s, where
        the hover solution is trivial and the feedforward adds nothing."""
        from scipy.spatial.transform import Rotation as _Rot
        import os
        wind = self.wind if self.TRIM_FF_TRUE_WIND else self._wind_vel_estimate()
        v_rel = self.target_vel - wind
        s = float(np.linalg.norm(v_rel))
        if s < 2.0:
            return None
        if self._trim_table is None:
            self._trim_table = dict(np.load(os.path.join(os.path.dirname(
                os.path.abspath(__file__)), "trim_table.npz")))
        t = self._trim_table
        g = float(np.arcsin(np.clip(v_rel[2] / s, -1.0, 1.0)))
        i = int(np.argmin(np.abs(t["speeds"] - s)))
        j = int(np.argmin(np.abs(t["gammas"] - g)))
        psi = float(np.arctan2(v_rel[1], v_rel[0]))
        R_tab = _Rot.from_euler("z", psi) * _Rot.from_rotvec(t["rotvecs"][i, j])
        sol = self._refine_trim(R_tab, float(t["des"][i, j]), v_rel)
        # a feedforward REFERENCE must be right: ~8% of draws leave the table warm-start in a
        # poor basin, so re-scan those (once per episode, only when needed).
        if self._ff_residual(sol, v_rel) > 0.5:
            best = sol
            best_r = self._ff_residual(sol, v_rel)
            for _ in range(12):
                R0 = _Rot.from_rotvec(self.np_random.normal(size=3) * 1.2) * R_tab
                cand = self._refine_trim(R0, float(t["des"][i, j]), v_rel)
                r = self._ff_residual(cand, v_rel)
                if r < best_r:
                    best, best_r = cand, r
                if best_r <= 0.05:
                    break
            sol = best
        return sol

# rate_vel_aviary.py — NEW method _ff_residual():
    def _ff_residual(self, sol, v_rel):
        """Residual acceleration (m/s^2) left by a candidate trim under THIS episode's draw."""
        R, de, T = sol
        Rm = R.as_matrix()
        v_xw = self._P_XW @ (Rm.T @ v_rel)
        Va = float(np.linalg.norm(v_xw))
        if Va < 1e-4:
            return 0.0
        u, vv, w = v_xw
        al = float(np.arctan2(-vv, u))
        be = float(np.arcsin(np.clip(w / Va, -1.0, 1.0)))
        F, _ = func_aero_model(al, be, Va, np.zeros(3), self.RHO, self.AERO_S, self.AERO_C,
                               self.AERO_B, (self.XG, self.YG, self.ZG), de, de, self.aero_rand)
        Fw = Rm @ (self._P_XW.T @ F) + np.array([0.0, 0.0, -self.M * 9.8]) + Rm[:, 2] * T
        return float(np.linalg.norm(Fw)) / self.M

# rate_vel_aviary.py — NEW method _wind_vel_estimate() (used only when trim_ff_true_wind=False):
    def _wind_vel_estimate(self):
        """Deployable stand-in for the wind VELOCITY: the disturbance observer estimates an
        external force; at quasi-steady flight the wind-induced part is recovered by
        differencing ground velocity against the axial air-relative speed the pitot sees."""
        R = np.array(p.getMatrixFromQuaternion(self.quat[0])).reshape(3, 3)
        axial = R[:, 2]
        pitot = float(axial @ (self.vel[0] - self.wind))    # sensor reading (axial airspeed)
        return self.vel[0] - pitot * axial

# train.py — flags (NEW):
    ap.add_argument("--trim-ff", action="store_true",
                    help="TRIM FEEDFORWARD: solve the episode's trim once at reset; the "
                         "policy commands only the deviation from it (a=0 holds trim)")
    ap.add_argument("--trim-ff-k", type=float, default=0.4,
                    help="tilt deviation scale for --trim-ff (max ~atan(k))")
    ap.add_argument("--trim-ff-thrust", type=float, default=0.4,
                    help="thrust deviation span for --trim-ff, x NOMINAL_HOVER")
    ap.add_argument("--trim-ff-fin", type=float, default=0.5,
                    help="elevon deviation span for --trim-ff, x FIN_MAX")
    ap.add_argument("--trim-ff-est-wind", action="store_true",
                    help="index the feedforward trim with the observer's wind estimate "
                         "(deployable) instead of the true wind (privileged ceiling test)")
# config keys trim_ff / trim_ff_k / trim_ff_thrust / trim_ff_fin / trim_ff_true_wind;
# eval_velyaw.py and continue_train.py pass all five through.
```

## Command
```bash
python train.py --xwing-aero --yaw-bias 0.3 --max-speed 25 --speed-min 18 --wind-max 15 \
  --yaw-gate --yaw-att-gate --vel-precision 0.7 --cov-width 5 --ent-coef 0.003 \
  --trim-init 0.3 --att-cmd --trim-ff --katt 3.0 --kp-rate 40,40,25 --ki-rate 10,10,5 \
  --n-envs 6 --timesteps 8000000 --out-dir results_velyaw_xw67
# then +4M @1e-4, then robust-gated +8M stages with --wind-oversample 0.5
```

## Pre-registered (vs the pure-RL champion xw51b: 2.03 median, 23% <1)
- **SUCCESS**: median <1.0 -> the architecture solves the fast bands; roll out to 25–34 and
  34–45, rebuild the composite, and quantify the deployable-wind cost (trial 68).
- **PROGRESS**: 1.0–1.7 -> real gain over pure RL; ladder further and report the hybrid
  trade honestly.
- **FAILURE**: >=1.9 -> even with a perfect reference and privileged wind the policy cannot
  hold trim at speed. That would relocate the limit to the inner loop's ability to stabilise
  an unstable equilibrium, not the policy's knowledge of where to fly.

## Result
*(auto-appended)*

## CANCELLED BY USER (2026-08-05) — "i don't need trim. i need only pure RL."
Killed ~40 min into training; no results produced or used. The code remains in the repo
behind `--trim-ff` (default OFF), so nothing in the pure-RL path is affected and the option
is recoverable if the deployment constraint ever changes. Trial 68 (deployable-wind variant)
never started.
