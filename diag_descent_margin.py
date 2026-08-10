"""Is the fast-band deficit a THRUST-AUTHORITY BOUNDARY at commanded descents?

Evidence that prompted this: the 25-34 champion tracks climbs at ~2.3 m/s error and fails
descents at ~10-14 (50%+ of steep-descent episodes exceed 10 m/s), and the failures are ~6 m/s
SHORT on descent rate. The nominal trim table shows why that might be structural: holding a
steep descent above ~18 m/s needs the throttle CLOSED (T ~ 0 N), so the aircraft sits on the
T >= 0 constraint boundary with no margin to reduce thrust further.

A trim that exists at nominal coefficients is not enough — the aircraft flies under +-20% aero
DR and 0-15 m/s wind. This re-solves trim PER DRAW and reports:
  * infeasible % : draws with no force balance at all (residual > 0.05 m/s^2)
  * T at floor % : draws whose trim demands the throttle fully closed (no downward authority)
  * median T     : the thrust margin actually available

    python diag_descent_margin.py
"""
import numpy as np
from scipy.spatial.transform import Rotation

import build_trim_table as B

SPEEDS = [12.0, 16.0, 20.0, 24.0, 28.0, 32.0]
GAMMAS_DEG = [-40.0, -30.0, -20.0, -10.0, 0.0, 20.0, 40.0]
NDRAW = 24


def main():
    z = np.load("trim_table.npz")
    tsp, tga, rot, des = z["speeds"], z["gammas"], z["rotvecs"], z["des"]
    rng = np.random.default_rng(0)
    draws = [(rng.uniform(0.8, 1.2, 17), float(rng.uniform(13.6, 14.1)))
             for _ in range(NDRAW)]

    print(f"per-draw trim feasibility under +-20% aero DR and mass 13.6-14.1 kg "
          f"({NDRAW} draws/cell)")
    print("\nINFEASIBLE % — no force balance exists for that draw (residual > 0.05 m/s^2)")
    hdr = "  V  " + "".join(f"{g:>8.0f}" for g in GAMMAS_DEG)
    print(hdr); print("-" * len(hdr))
    infeas = {}
    floor = {}
    medT = {}
    for V in SPEEDS:
        i = int(np.argmin(np.abs(tsp - V)))
        rowa, rowb, rowc = [], [], []
        for gd in GAMMAS_DEG:
            g = np.radians(gd)
            j = int(np.argmin(np.abs(tga - g)))
            v_rel = V * np.array([np.cos(g), 0.0, np.sin(g)])
            x0 = np.concatenate([rot[i, j], [des[i, j]]])
            bad = 0; atfloor = 0; Ts = []
            for aero, m in draws:
                f = lambda x: B.residual(x, v_rel, rand=aero, m=m)[0]
                from scipy.optimize import minimize
                r = minimize(f, x0, method="Nelder-Mead",
                             options={"maxiter": 2000, "xatol": 1e-6, "fatol": 1e-8})
                res, T = B.residual(r.x, v_rel, rand=aero, m=m)
                if res / m > 0.05:
                    bad += 1
                if T < 1.0:
                    atfloor += 1
                Ts.append(T)
            rowa.append(bad / len(draws) * 100)
            rowb.append(atfloor / len(draws) * 100)
            rowc.append(float(np.median(Ts)))
        infeas[V], floor[V], medT[V] = rowa, rowb, rowc
        print(f"{V:>4.0f} " + "".join(f"{x:>7.0f}%" for x in rowa))

    print("\nTHROTTLE AT FLOOR % — trim needs T < 1 N: thrust can only be ADDED, not removed")
    print(hdr); print("-" * len(hdr))
    for V in SPEEDS:
        print(f"{V:>4.0f} " + "".join(f"{x:>7.0f}%" for x in floor[V]))

    print("\nMEDIAN TRIM THRUST (N) — the two-sided authority margin")
    print(hdr); print("-" * len(hdr))
    for V in SPEEDS:
        print(f"{V:>4.0f} " + "".join(f"{x:>8.1f}" for x in medT[V]))


if __name__ == "__main__":
    main()
