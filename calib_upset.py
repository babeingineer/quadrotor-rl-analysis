"""Calibrate the upset detector against DATA instead of one band's intuition.

The hand-set thresholds (tilt past 84 deg, body rate > 2.5 rad/s, excess sink > 15 m/s) were
tuned on the mid champion, where they fired on 18% of nominal flights. Across the whole
roster they fire on 47%, because:
  * a tailsitter's normal CRUISE is near-horizontal — nominal tilt p95 reaches 92-110 deg at
    18-34 m/s, so an absolute tilt limit calls fast flight an upset. The expected tilt is a
    function of commanded speed, and the trim table already knows it.
  * these policies are aggressive: they exceed 2.5 rad/s on 6-17% of nominal steps.

So: record features on nominal AND upset episodes once, then sweep thresholds offline (free)
and pick an operating point by measured separation. Firing is scored WITH dwell, per episode,
because that is how the switch actually decides.

    python calib_upset.py                 # record + sweep
    python calib_upset.py --sweep-only    # re-sweep saved trajectories
"""
import argparse
import os

import numpy as np
import pybullet as p_bullet
from scipy.spatial.transform import Rotation

from eval_composite import ROSTER
from recovery_switch import act, apply_cfg, build_env, load_policy, reset_episode

CACHE = "upset_calib.npz"


def tilt_reference():
    """Expected tilt (deg) at trim, as a function of (speed, climb angle), from the trim table."""
    z = np.load("trim_table.npz")
    speeds, gammas, rotvecs = z["speeds"], z["gammas"], z["rotvecs"]
    tilt = np.zeros((len(speeds), len(gammas)))
    for i in range(len(speeds)):
        for j in range(len(gammas)):
            R = Rotation.from_rotvec(rotvecs[i, j]).as_matrix()
            tilt[i, j] = np.degrees(np.arccos(np.clip(R[2, 2], -1.0, 1.0)))
    return speeds, gammas, tilt


def expected_tilt(speeds, gammas, tilt, speed, gamma):
    """Bilinear-ish lookup: interpolate over speed at the nearest commanded climb angle."""
    j = int(np.argmin(np.abs(gammas - gamma)))
    return float(np.interp(speed, speeds, tilt[:, j]))


def record(n_nom, n_up, ep_len):
    speeds, gammas, tref = tilt_reference()
    cols = {}
    for lo, hi, d in ROSTER:
        nom = load_policy(d)
        for kind, count, upset, seed0 in (("nom", n_nom, False, 5000),
                                          ("up", n_up, True, 1000)):
            env = build_env(nom["cfg"], ep_len, lo, hi, upset=upset)
            dt = env.CTRL_TIMESTEP
            N = int(ep_len / dt)
            rec = []
            for i in range(count):
                reset_episode(env, seed0 + i, lo, hi)
                tsp = float(np.linalg.norm(env.target_vel))
                gam = np.degrees(np.arcsin(np.clip(env.target_vel[2] / max(tsp, 1e-6), -1, 1)))
                exp_t = expected_tilt(speeds, gammas, tref, tsp, gam)
                for k in range(N):
                    apply_cfg(env, nom)
                    _, _, term, trunc, info = env.step(act(env, nom))
                    R = np.array(p_bullet.getMatrixFromQuaternion(env.quat[0])).reshape(3, 3)
                    rec.append((i,
                                np.degrees(np.arccos(np.clip(float(R[2, 2]), -1, 1))),
                                exp_t,
                                float(env.target_vel[2] - env.vel[0][2]),
                                float(np.linalg.norm(env.ang_v[0])),
                                info["vel_error"], tsp))
                    if term or trunc:
                        break
            env.close()
            cols[f"{d}|{kind}"] = np.array(rec, dtype=np.float64)
            print(f"  recorded {d} {kind}: {count} eps, {len(rec)} steps")
    np.savez_compressed(CACHE, **cols)
    return cols


def fires(a, tilt_margin, sink_thr, rate_thr, arm_steps):
    """Per-episode: does the detector engage, with dwell, anywhere in the episode?"""
    ep = a[:, 0]
    cond = ((a[:, 1] > a[:, 2] + tilt_margin) | (a[:, 3] > sink_thr) | (a[:, 4] > rate_thr))
    out = []
    for e in np.unique(ep):
        c = cond[ep == e]
        run = hot = 0
        for v in c:
            hot = hot + 1 if v else 0
            run = max(run, hot)
        out.append(run >= arm_steps)
    return np.array(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nominal-eps", type=int, default=30)
    ap.add_argument("--upsets", type=int, default=30)
    ap.add_argument("--ep-len", type=float, default=8.0)
    ap.add_argument("--sweep-only", action="store_true")
    args = ap.parse_args()

    if args.sweep_only and os.path.exists(CACHE):
        cols = dict(np.load(CACHE))
    else:
        cols = record(args.nominal_eps, args.upsets, args.ep_len)

    print("\nsweep: tilt margin over trim / sink / rate / dwell — per-episode firing")
    print(f"{'tiltM':>6}{'sink':>6}{'rate':>6}{'arm_s':>7} | "
          f"{'nominal FP (per band)':<34}{'upset TP':>10}")
    print("-" * 70)
    grid = []
    for tm in (45, 60, 75):
        for sk in (20.0, 25.0, 30.0):
            for rt in (6.0, 8.0, 10.0):
                for arm in (0.4, 0.8, 1.2):
                    fp, tp, per = [], [], []
                    for lo, hi, d in ROSTER:
                        n = fires(cols[f"{d}|nom"], tm, sk, rt, int(arm * 50))
                        u = fires(cols[f"{d}|up"], tm, sk, rt, int(arm * 50))
                        per.append(f"{n.mean() * 100:.0f}%")
                        fp.append(n.mean()); tp.append(u.mean())
                    fpm, tpm = float(np.mean(fp)), float(np.mean(tp))
                    worst = max(fp)
                    grid.append({"fp": fpm, "tp": tpm, "worst": worst, "tm": tm,
                                 "sk": sk, "rt": rt, "arm": arm, "per": per})
    # Pareto front on (nominal FP down, upset TP up): the operating curve, not one point.
    front = [g for g in grid
             if not any(h["fp"] <= g["fp"] and h["tp"] >= g["tp"] and h != g
                        and (h["fp"] < g["fp"] or h["tp"] > g["tp"]) for h in grid)]
    for g in sorted(front, key=lambda x: x["fp"]):
        print(f"{g['tm']:>6}{g['sk']:>6.0f}{g['rt']:>6.1f}{g['arm']:>7.1f} | "
              f"{' '.join(f'{x:>7}' for x in g['per']):<34}{g['tp'] * 100:>9.0f}%"
              f"   (FP mean {g['fp'] * 100:.0f}%, worst band {g['worst'] * 100:.0f}%)")
    ok = [g for g in front if g["tp"] >= 0.85]
    pick = min(ok or front, key=lambda g: g["fp"])
    print(f"\npick (TP>=85%, lowest FP): tilt +{pick['tm']} deg over trim, sink {pick['sk']:g}, "
          f"rate {pick['rt']:g}, arm {pick['arm']:g}s -> FP {pick['fp'] * 100:.0f}% "
          f"(worst band {pick['worst'] * 100:.0f}%), upset detect {pick['tp'] * 100:.0f}%")
    print("NOTE: upset TP is detector engagement, not recovery success — recovery is measured "
          "by eval_recovery_switch/eval_composite once a threshold set is chosen.")


if __name__ == "__main__":
    main()
