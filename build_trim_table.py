"""Build the canonical trim table used for trim-initialized training.

Solves nominal-coefficient trim (attitude R, elevator de, thrust T) over a grid of
air-relative speed x flight-path angle, in the canonical frame (v_rel in the x-z plane).
At runtime the env rotates the entry about world-z to the episode's actual v_rel heading.
Grid solves are warm-started from the previous neighbor, so the whole table takes ~1 min.

Also reports the residual acceleration of table trims under RANDOM +/-20% DR draws,
i.e. how 'near-trim' the cached starts actually are for a randomized episode.

    python build_trim_table.py            # writes trim_table.npz
"""
import numpy as np
from scipy.spatial.transform import Rotation
from scipy.optimize import minimize
from aero_xwing import func_aero_model

RHO, S, C, B = 1.225, 1.0, 1.0, 1.0
XG, YG, ZG = 0.4045, 0.0, 0.0
M_NOM, G0, MAX_T = 13.85, 9.8, 440.0
FIN_MAX = np.radians(20.0)
P_XW = np.array([[0.0, 0.0, 1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])

SPEEDS = np.arange(2.0, 61.0, 2.0)            # 30 values (45 m/s targets + 15 m/s wind)
GAMMAS = np.radians(np.arange(-40.0, 41.0, 10.0))   # 9 values


def residual(x, v_rel, rand=None, m=M_NOM):
    rand = np.ones(17) if rand is None else rand
    R = Rotation.from_rotvec(x[:3]).as_matrix()
    de = float(np.clip(x[3], -FIN_MAX, FIN_MAX))
    v_xw = P_XW @ (R.T @ v_rel)
    Va = float(np.linalg.norm(v_xw))
    G = np.array([0.0, 0.0, -m * G0])
    if Va < 1e-4:
        Fw = G
    else:
        u, vv, w = v_xw
        al = float(np.arctan2(-vv, u))
        be = float(np.arcsin(np.clip(w / Va, -1.0, 1.0)))
        F, _ = func_aero_model(al, be, Va, np.zeros(3), RHO, S, C, B, (XG, YG, ZG), de, de, rand)
        Fw = R @ (P_XW.T @ F) + G
    bz = R[:, 2]
    T = float(np.clip(-(Fw @ bz), 0.0, MAX_T))
    return float(np.linalg.norm(Fw + T * bz)), T


def solve(v_rel, x0):
    f = lambda x: residual(x, v_rel)[0]
    res = minimize(f, x0, method="Nelder-Mead",
                   options={"maxiter": 3000, "xatol": 1e-7, "fatol": 1e-9})
    r, T = residual(res.x, v_rel)
    return res.x, r, T


def main():
    rng = np.random.default_rng(3)
    coarse = Rotation.random(2000, random_state=rng).as_matrix()
    rotvecs = np.zeros((len(SPEEDS), len(GAMMAS), 3))
    des = np.zeros((len(SPEEDS), len(GAMMAS)))
    thrusts = np.zeros((len(SPEEDS), len(GAMMAS)))
    resids = np.zeros((len(SPEEDS), len(GAMMAS)))
    x_prev = None
    for i, s in enumerate(SPEEDS):
        for j, g in enumerate(GAMMAS):
            v_rel = s * np.array([np.cos(g), 0.0, np.sin(g)])
            if x_prev is None:                     # first cell: coarse scan
                best = (1e18, None)
                for R in coarse:
                    x = np.concatenate([Rotation.from_matrix(R).as_rotvec(), [0.0]])
                    r, _ = residual(x, v_rel)
                    if r < best[0]:
                        best = (r, x)
                x0 = best[1]
            else:
                x0 = x_prev
            x, r, T = solve(v_rel, x0)
            if r / M_NOM > 0.05 and x_prev is not None:   # warm-start trapped: re-scan
                best = (1e18, None)
                for R in coarse:
                    xx = np.concatenate([Rotation.from_matrix(R).as_rotvec(), [0.0]])
                    rr, _ = residual(xx, v_rel)
                    if rr < best[0]:
                        best = (rr, xx)
                x, r, T = solve(v_rel, best[1])
            rotvecs[i, j], des[i, j], thrusts[i, j], resids[i, j] = x[:3], x[3], T, r / M_NOM
            x_prev = x if j < len(GAMMAS) - 1 else rotvecs[i, 0].tolist() + [des[i, 0]]
        x_prev = np.concatenate([rotvecs[i, 0], [des[i, 0]]])
    np.savez("trim_table.npz", speeds=SPEEDS, gammas=GAMMAS, rotvecs=rotvecs,
             des=des, thrusts=thrusts, resids=resids)
    print(f"table built: {resids.size} cells, nominal residual max {resids.max():.3f} m/s^2")

    # residual of TABLE trims under random +/-20% DR draws (mid-band speeds)
    errs = []
    for _ in range(200):
        s = rng.uniform(10, 25)
        g = rng.uniform(-0.3, 0.3)
        v_rel = s * np.array([np.cos(g), 0.0, np.sin(g)])
        i = int(np.argmin(np.abs(SPEEDS - s)))
        j = int(np.argmin(np.abs(GAMMAS - g)))
        x = np.concatenate([rotvecs[i, j], [des[i, j]]])
        rand = 1.0 + rng.uniform(-0.2, 0.2, size=17)
        m = rng.uniform(13.6, 14.1)
        r, _ = residual(x, v_rel, rand=rand, m=m)
        errs.append(r / m)
    e = np.array(errs)
    print(f"table trim under random DR draw: residual mean {e.mean():.2f}  median "
          f"{np.median(e):.2f}  p90 {np.percentile(e, 90):.2f} m/s^2 "
          f"(this is the 'near-trim' start quality for training)")


if __name__ == "__main__":
    main()
