"""Can the policy HOLD a commanded descent, or only fail to ENTER one?

Three mechanisms are already refuted for the descent asymmetry (thrust floor: only bites at
gamma<=-30 but the penalty is smooth; trim tilt: the low band shows the asymmetry at constant
tilt; settling time: 20 s episodes leave the gap slightly WIDER than 8 s). What remains is
whether the deficit is ENTRY (the aircraft cannot get into a steep descent from a hover start)
or STABILIZATION (it cannot hold one even when placed there).

This is the trial-27 discriminator applied to direction: start episodes AT the commanded
velocity in near-trim attitude (trim_init_frac=1.0) and compare per-angle error against the
same policy started from rest.

  * hold is fine, rest-start fails  -> ENTRY problem (a maneuver/transition deficit)
  * hold also fails                 -> STABILIZATION problem (the trim is not holdable)

    python diag_descent_hold.py --dir results_velyaw_xw55a --lo 25 --hi 34 --episodes 240
"""
import argparse

import numpy as np

from eval_velyaw import load


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="results_velyaw_xw55a")
    ap.add_argument("--lo", type=float, default=25.0)
    ap.add_argument("--hi", type=float, default=34.0)
    ap.add_argument("--episodes", type=int, default=240)
    ap.add_argument("--ep-len", type=float, default=8.0)
    args = ap.parse_args()

    model, venv, base = load(args.dir, args.ep_len, speed_min=args.lo, max_speed=args.hi,
                             randomize_init=True, trim_init_frac=1.0, tough_init_frac=0.0)
    dt = base.CTRL_TIMESTEP
    N = int(args.ep_len / dt)
    k0 = N - int(3.0 / dt)
    rows = []
    for i in range(args.episodes):
        venv.seed(40000 + i)
        obs = venv.reset()
        model.reset()
        tv = base.target_vel.copy()
        V = float(np.linalg.norm(tv))
        gd = np.degrees(np.arcsin(np.clip(tv[2] / max(V, 1e-6), -1, 1)))
        v0 = float(np.linalg.norm(base.vel[0] - tv))     # confirm we really started at target
        vels = []
        for k in range(N):
            a, _ = model.predict(obs, deterministic=True)
            obs, _, done, infos = venv.step(a)
            if k >= k0:
                vels.append(base.vel[0].copy())
            if done[0]:
                break
        if not vels:
            continue
        vm = np.mean(vels, axis=0)
        rows.append((gd, float(np.linalg.norm(vm - tv)), v0, float(vm[2] - tv[2])))

    venv.close()
    a = np.array(rows)
    print(f"{args.dir}  band {args.lo:g}-{args.hi:g}  TRIM-START (hold test)  n={len(a)}")
    print(f"start-at-target check: median |v0 - target| = {np.median(a[:, 2]):.2f} m/s "
          f"(small = episodes really begin in the commanded state)")
    print(f"\n{'gamma bin':<14}{'n':>4}{'median err':>12}{'%>10':>7}{'vert err':>10}")
    print("-" * 48)
    for lo, hi in ((-45, -25), (-25, -10), (-10, 10), (10, 25), (25, 45)):
        m = (a[:, 0] >= lo) & (a[:, 0] < hi)
        if m.sum() > 2:
            print(f"{f'{lo:+d} to {hi:+d}':<14}{m.sum():>4}{np.median(a[m, 1]):>12.2f}"
                  f"{np.mean(a[m, 1] > 10) * 100:>6.0f}%{np.mean(a[m, 3]):>10.2f}")
    d = a[a[:, 0] < -10, 1]
    c = a[a[:, 0] > 10, 1]
    print(f"\ndescents n={len(d)} median {np.median(d):.2f}   "
          f"climbs n={len(c)} median {np.median(c):.2f}   ratio {np.median(d) / np.median(c):.2f}x")
    print("compare rest-start (8 s): vhigh descents 10.16 vs climbs 2.44 = 4.2x")


if __name__ == "__main__":
    main()
