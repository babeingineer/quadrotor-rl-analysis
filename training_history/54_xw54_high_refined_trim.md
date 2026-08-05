# Trial 54 — xw54: high band with REFINED trim-init + full ladder

## Why
18–25 polish stalled at 2.03 (xw51b). Untested lever: **per-episode trim refinement** —
the table trim is nominal-coefficient, and its residual under DR grows with Q
(0.76 m/s² at Va 10–20 → 1.08 at 20–30 → 3.02 at 40–55), so goal-state exposure was
degrading exactly where we stall. Reset now warm-starts a short solve against the
episode's own aero draw (0.04 s/reset). Dose raised 0.2→0.3.
Also refuted for this band: teacher–student (classical is 3.90 here vs our 2.03),
body-relative attitude command (drifts: no absolute reference), 100 Hz, band split,
airflow obs, authority-II, integral memory.

## Pre-registered (vs xw51b 2.03)
- SUCCESS: median <1 → band at goal.
- PROGRESS: ≤1.7 → keep laddering.
- FAILURE: ≥1.9 → refinement isn't the lever either; the honest capability statement
  for 18–25 stands at ~2.0 and effort moves to envelope coverage + composite.

## Exact code changes
```python
# rate_vel_aviary.py — _apply_trim_init() (CHANGED: table entry is now refined against
# the episode's actual DR draw before use):
        R_tab = _Rot.from_euler("z", psi) * R_can
        de_tab = float(t["des"][i, j])
        R_ref, de_ref, T_ref = self._refine_trim(R_tab, de_tab, v_rel)
        scatter = _Rot.from_rotvec(self.np_random.normal(size=3) * np.radians(10.0) / 1.732)
        R = R_ref * scatter
        ...
        self.fin_angles = np.array([de_ref, de_ref])
        self.motor_forces = np.full(4, T_ref / 4.0)

# rate_vel_aviary.py — NEW method:
    def _refine_trim(self, R_tab, de_tab, v_rel):
        """Short warm-started solve of (attitude, elevator) against THIS episode's actual
        aero draw and mass; returns (R, de, total thrust)."""
        from scipy.spatial.transform import Rotation as _Rot
        from scipy.optimize import minimize as _min
        G = np.array([0.0, 0.0, -self.M * 9.8])

        def resid(x):
            R = _Rot.from_rotvec(x[:3]).as_matrix()
            de = float(np.clip(x[3], -self.FIN_MAX, self.FIN_MAX))
            v_xw = self._P_XW @ (R.T @ v_rel)
            Va = float(np.linalg.norm(v_xw))
            if Va < 1e-4:
                Fw = G
            else:
                u, vv, w = v_xw
                al = float(np.arctan2(-vv, u))
                be = float(np.arcsin(np.clip(w / Va, -1.0, 1.0)))
                F, _ = func_aero_model(al, be, Va, np.zeros(3), self.RHO, self.AERO_S,
                                       self.AERO_C, self.AERO_B, (self.XG, self.YG, self.ZG),
                                       de, de, self.aero_rand)
                Fw = R @ (self._P_XW.T @ F) + G
            bz = R[:, 2]
            T = float(np.clip(-(Fw @ bz), 0.0, self.MAX_TOTAL_THRUST))
            return float(np.linalg.norm(Fw + T * bz)), T

        x0 = np.concatenate([R_tab.as_rotvec(), [de_tab]])
        try:
            res = _min(lambda x: resid(x)[0], x0, method="Nelder-Mead",
                       options={"maxiter": 150, "xatol": 1e-4, "fatol": 1e-3})
            x = res.x
        except Exception:
            x = x0
        _, T = resid(x)
        return (_Rot.from_rotvec(x[:3]),
                float(np.clip(x[3], -self.FIN_MAX, self.FIN_MAX)), T)
```
Measured cost: 0.04 s per reset. Measured need: table-trim residual under DR grows
0.76 m/s^2 (Va 10-20) -> 1.08 (20-30) -> 1.27 (30-40) -> 3.02 (40-55).

### Also implemented in this window and REJECTED (kept, default off): att_rel
```python
# rate_vel_aviary.py — constructor args (NEW):
                 att_rel: bool = False,            # att_cmd variant: commanded thrust
                 #                                   direction is BODY-RELATIVE
                 att_rel_k: float = 0.5,           # max per-step tilt correction = atan(k)

# rate_vel_aviary.py — step(), att_cmd decode (CHANGED):
        if self.ATT_CMD:
            xy = self.current_action[-3:-1]
            if self.ATT_REL:
                # body-relative: a=0 holds the current thrust axis; max correction atan(k)
                R0 = np.array(p.getMatrixFromQuaternion(self.quat[0])).reshape(3, 3)
                v = np.array([self.ATT_REL_K * xy[0], self.ATT_REL_K * xy[1], 1.0])
                self._bz_des = R0 @ (v / np.linalg.norm(v))
            else:
                # world-frame upper hemisphere (norm<=0.985 caps tilt at ~80 deg)
                n = float(np.linalg.norm(xy))
                if n > 0.985:
                    xy = xy * (0.985 / n)
                self._bz_des = np.array([xy[0], xy[1], np.sqrt(max(1.0 - xy @ xy, 1e-6))])
            self._yaw_rate_des = float(self.current_action[-1]) * float(self.MAX_RATE[2])
# train.py: --att-rel / --att-rel-k; config keys att_rel / att_rel_k; eval+continue passthrough.
```
Rejected by smoke test (neutral action = "hold current attitude" -> no absolute reference;
98 deg drift in 3 s vs 35 deg for the world-frame form).

## VERDICT: FAILURE as designed — but a decisive negative about LINEAGE, not the lever
Fresh 18–25 with the best recipe + refined trim-init (dose 0.3): **5.07 median, 0% <1 @12M**
vs the transfer-lineage champion's 2.03. Compared at matched steps the gap is even starker:
transfer reached 2.39 in ONE 6M continuation from the mid champion, while fresh training
needs 12M to reach 5.07. **Fresh training at the high band is a dead end; band-extension
transfer is the mechanism.** Ladder killed at stage b to free the chain.
Note the refined trim-init was NOT isolated by this run (fresh-vs-transfer dominates), so
the lever moves to the champion lineage as trial 57 — xw51b's config already carries
trim_init 0.2, so the refinement (implemented after xw51 ran) now applies automatically.
