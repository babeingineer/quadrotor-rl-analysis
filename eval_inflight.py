"""Inflight-hold evaluation: start each eval episode already AT the target velocity, in
per-draw trim attitude (solved against the episode's actual aero_rand/mass/wind), and
measure hold error over the steady window.

Reading: hold-median << rest-start median -> the policy can hold trim but not approach/settle;
         hold-median ~  rest-start median -> the hold behavior itself is the limitation.

    python eval_inflight.py --dir results_velyaw_xw26b --episodes 60 --ep-len 20
"""
import argparse
import numpy as np
import pybullet as p
from scipy.spatial.transform import Rotation
from scipy.optimize import minimize
from aero_xwing import func_aero_model
from eval_velyaw import load

_COARSE = Rotation.random(1500, random_state=np.random.default_rng(7)).as_matrix()


def solve_trim(env):
    """Trim (R, thrust, elevator) for THIS episode's draw: target_vel, wind, aero_rand, mass."""
    P = env._P_XW
    v_rel = env.target_vel - env.wind
    G = np.array([0.0, 0.0, -env.M * 9.8])
    maxT = env.MAX_TOTAL_THRUST

    def residual(x):
        R = Rotation.from_rotvec(x[:3]).as_matrix()
        de = float(np.clip(x[3], -env.FIN_MAX, env.FIN_MAX))
        v_xw = P @ (R.T @ v_rel)
        Va = float(np.linalg.norm(v_xw))
        if Va < 1e-4:
            Fw = G
        else:
            u, vv, w = v_xw
            al = float(np.arctan2(-vv, u))
            be = float(np.arcsin(np.clip(w / Va, -1.0, 1.0)))
            F, _ = func_aero_model(al, be, Va, np.zeros(3), env.RHO, env.AERO_S, env.AERO_C,
                                   env.AERO_B, (env.XG, env.YG, env.ZG), de, de, env.aero_rand)
            Fw = R @ (P.T @ F) + G
        bz = Rotation.from_rotvec(x[:3]).as_matrix()[:, 2]
        T = float(np.clip(-(Fw @ bz), 0.0, maxT))
        return float(np.linalg.norm(Fw + T * bz))

    best = (1e18, None)
    for R in _COARSE:
        r = residual(np.concatenate([Rotation.from_matrix(R).as_rotvec(), [0.0]]))
        if r < best[0]:
            best = (r, R)
    x0 = np.concatenate([Rotation.from_matrix(best[1]).as_rotvec(), [0.0]])
    res = minimize(residual, x0, method="Nelder-Mead",
                   options={"maxiter": 2000, "xatol": 1e-6, "fatol": 1e-8})
    R = Rotation.from_rotvec(res.x[:3])
    de = float(np.clip(res.x[3], -env.FIN_MAX, env.FIN_MAX))
    return R, de, res.fun / env.M


def evaluate_inflight(D, n=60, ep_len=20.0, steady_window=3.0, **overrides):
    model, venv, base = load(D, ep_len, **overrides)
    dt = base.CTRL_TIMESTEP
    N = int(ep_len / dt)
    k0 = N - int(steady_window / dt)
    rows = []
    for i in range(n):
        venv.seed(1000 + i)
        obs = venv.reset()
        model.reset()
        R, de, resid = solve_trim(base)
        did = int(base.DRONE_IDS[0])
        quat = R.as_quat()                                   # xyzw
        p.resetBasePositionAndOrientation(did, base.pos[0].tolist(), quat.tolist(),
                                          physicsClientId=base.CLIENT)
        p.resetBaseVelocity(did, base.target_vel.tolist(), [0, 0, 0],
                            physicsClientId=base.CLIENT)
        base.fin_angles = np.array([de, de])                 # elevons pre-set at trim
        base._updateAndStoreKinematicInformation()
        try:                                                  # fresh obs from the trim state
            raw = base._computeObs().reshape(1, -1)
            obs = venv.normalize_obs(raw)
        except Exception:
            pass                                              # fall back: one stale-obs step
        tgt = float(np.linalg.norm(base.target_vel))
        errs = []
        for k in range(N):
            a, _ = model.predict(obs, deterministic=True)
            obs, _, done, infos = venv.step(a)
            if k >= k0:
                errs.append(infos[0]["vel_error"])
            if done[0]:
                break
        rows.append((tgt, float(np.linalg.norm(base.wind)), resid,
                     np.mean(errs) if errs else np.nan))
    venv.close()
    return rows


def report(rows, tag):
    e = np.array([r[3] for r in rows if not np.isnan(r[3])])
    print(f"\n=== INFLIGHT-HOLD {tag}: n={len(e)} ===")
    print(f"mean {e.mean():.2f}  median {np.median(e):.2f}  <1m/s {np.mean(e < 1) * 100:.0f}%"
          f"  p90 {np.percentile(e, 90):.2f}")
    bad = [r for r in rows if r[2] > 0.5]
    if bad:
        print(f"({len(bad)} eps had trim residual >0.5 m/s^2 — solver misses, treat separately)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="results_velyaw_xw26b")
    ap.add_argument("--episodes", type=int, default=60)
    ap.add_argument("--ep-len", type=float, default=20.0)
    args = ap.parse_args()
    rows = evaluate_inflight(args.dir, n=args.episodes, ep_len=args.ep_len)
    report(rows, args.dir)
