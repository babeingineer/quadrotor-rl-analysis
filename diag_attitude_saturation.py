"""Is the descent failure an ACTION-SPACE limit rather than a control failure?

The att_cmd decode builds the desired thrust axis as
    bz_des = [x, y, sqrt(1 - x^2 - y^2)],  |xy| <= 0.985
so bz_des.z >= 0 always: the command is confined to the UPPER HEMISPHERE and tilt is capped at
arccos(sqrt(1-0.985^2)) = 80.0 deg. Trial 75 measured the trim tilt required for steep descents
at 88.9 deg (28 m/s) and 93-105 deg (>=32 m/s) — i.e. BEYOND the cap, and past 90 deg it is in
the lower hemisphere, unreachable by this parameterisation at any action value.

This logs, per step, the COMMANDED tilt (from bz_des), the ACHIEVED tilt, and the trim tilt the
command implies, for forced climbs and descents. Predictions if the cap is the cause:
  * commanded tilt pins at ~80 deg in steep descents and sits well below it in climbs
  * achieved tilt tracks commanded (the inner loop is fine) but both fall short of trim
  * the shortfall grows with commanded speed

    python diag_attitude_saturation.py --dir results_velyaw_xw55a --lo 25 --hi 34
"""
import argparse

import numpy as np

from eval_velyaw import load
from recovery_switch import expected_tilt

CAP_DEG = np.degrees(np.arccos(np.sqrt(max(1.0 - 0.985 ** 2, 1e-9))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="results_velyaw_xw55a")
    ap.add_argument("--lo", type=float, default=25.0)
    ap.add_argument("--hi", type=float, default=34.0)
    ap.add_argument("--per-angle", type=int, default=10)
    ap.add_argument("--ep-len", type=float, default=8.0)
    args = ap.parse_args()

    model, venv, base = load(args.dir, args.ep_len, speed_min=args.lo, max_speed=args.hi)
    dt = base.CTRL_TIMESTEP
    N = int(args.ep_len / dt)
    k0 = N - int(3.0 / dt)
    print(f"{args.dir}  att_cmd={base.ATT_CMD}   action-space tilt cap = {CAP_DEG:.1f} deg")
    print(f"\n{'gamma':>6}{'trim tilt':>11}{'cmd tilt':>10}{'achieved':>10}"
          f"{'cmd@cap%':>10}{'track err':>11}{'vel err':>9}")
    print("-" * 68)
    for gd in (-40, -30, -20, 0, 20, 40):
        g = np.radians(gd)
        rows = []
        for i in range(args.per_angle):
            venv.seed(30000 + i)
            obs = venv.reset()
            model.reset()
            rng = np.random.default_rng(30000 + i)
            psi = rng.uniform(0, 2 * np.pi)
            V = float(rng.uniform(args.lo, args.hi))
            tv = V * np.array([np.cos(g) * np.cos(psi), np.cos(g) * np.sin(psi), np.sin(g)])
            base.target_vel = tv.copy()
            treq = expected_tilt(tv)
            cmds, achs, errs = [], [], []
            for k in range(N):
                a, _ = model.predict(obs, deterministic=True)
                obs, _, done, infos = venv.step(a)
                base.target_vel = tv.copy()
                if k >= k0:
                    bz = base._bz_des
                    if bz is not None:
                        cmds.append(np.degrees(np.arccos(np.clip(bz[2], -1, 1))))
                    R = base._R_of() if hasattr(base, "_R_of") else None
                    import pybullet as pb
                    Rm = np.array(pb.getMatrixFromQuaternion(base.quat[0])).reshape(3, 3)
                    achs.append(np.degrees(np.arccos(np.clip(Rm[2, 2], -1, 1))))
                    errs.append(infos[0]["vel_error"])
                if done[0]:
                    break
            if cmds:
                rows.append((treq, np.mean(cmds), np.mean(achs),
                             np.mean(np.array(cmds) > CAP_DEG - 1.0) * 100,
                             np.mean(np.abs(np.array(achs) - np.array(cmds))),
                             np.mean(errs)))
        if rows:
            a = np.array(rows)
            print(f"{gd:>6}{a[:, 0].mean():>11.1f}{a[:, 1].mean():>10.1f}{a[:, 2].mean():>10.1f}"
                  f"{a[:, 3].mean():>9.0f}%{a[:, 4].mean():>11.1f}{a[:, 5].mean():>9.2f}")
    venv.close()
    print(f"\nIf 'cmd tilt' pins near {CAP_DEG:.0f} deg while 'trim tilt' exceeds it, the policy is "
          f"asking for\nthe steepest attitude the ACTION SPACE allows and still cannot reach trim "
          f"— an interface\nlimit, not a learning or inner-loop failure.")


if __name__ == "__main__":
    main()
