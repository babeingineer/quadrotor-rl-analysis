"""Stratified flight-path-angle sweep: is the fast-band deficit specific to DESCENTS, and is it
concentrated where the throttle hits its floor?

Random targets gave only ~11-31 episodes per angle bin — enough to see a climb/descent
asymmetry, not enough to tell "steep descents only" (which the thrust-floor analysis predicts:
throttle at floor 42% at gamma=-40 but 0% at gamma=-20) from "all descents" (which it doesn't).
This forces the commanded direction instead of sampling it, so every angle gets equal n.

The target is overridden AFTER reset, so the first action of each episode sees the reset's
target; with an 8 s episode scored over the last 3 s that is irrelevant, but it is why the
first step is not counted.

    python diag_gamma_sweep.py --dir results_velyaw_xw55a --lo 25 --hi 34 --per-angle 24
"""
import argparse

import numpy as np

from eval_velyaw import load

ANGLES = [-40, -30, -20, -10, 0, 10, 20, 30, 40]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="results_velyaw_xw55a")
    ap.add_argument("--lo", type=float, default=25.0)
    ap.add_argument("--hi", type=float, default=34.0)
    ap.add_argument("--per-angle", type=int, default=24)
    ap.add_argument("--ep-len", type=float, default=8.0)
    args = ap.parse_args()

    model, venv, base = load(args.dir, args.ep_len, speed_min=args.lo, max_speed=args.hi)
    dt = base.CTRL_TIMESTEP
    N = int(args.ep_len / dt)
    k0 = N - int(3.0 / dt)
    print(f"{args.dir}  band {args.lo:g}-{args.hi:g}  n={args.per_angle}/angle")
    print(f"\n{'gamma':>6}{'n':>4}{'median':>9}{'mean':>8}{'%<1':>6}{'%>10':>7}"
          f"{'vert err':>10}{'speed def':>11}{'dir err':>9}")
    print("-" * 70)
    out = {}
    for gd in ANGLES:
        g = np.radians(gd)
        errs, verts, defs, dirs = [], [], [], []
        for i in range(args.per_angle):
            venv.seed(30000 + i)
            obs = venv.reset()
            model.reset()
            rng = np.random.default_rng(30000 + i)
            psi = rng.uniform(0, 2 * np.pi)
            V = float(rng.uniform(args.lo, args.hi))
            tv = V * np.array([np.cos(g) * np.cos(psi), np.cos(g) * np.sin(psi), np.sin(g)])
            base.target_vel = tv.copy()
            vels = []
            for k in range(N):
                a, _ = model.predict(obs, deterministic=True)
                obs, _, done, infos = venv.step(a)
                base.target_vel = tv.copy()          # hold the override across the episode
                if k >= k0:
                    vels.append(base.vel[0].copy())
                if done[0]:
                    break
            if not vels:
                continue
            vm = np.mean(vels, axis=0)
            errs.append(float(np.linalg.norm(vm - tv)))
            verts.append(float(vm[2] - tv[2]))
            defs.append(V - float(np.linalg.norm(vm)))
            h1, h2 = vm[:2], tv[:2]
            dirs.append(np.degrees(np.arccos(np.clip(
                (h1 @ h2) / max(np.linalg.norm(h1) * np.linalg.norm(h2), 1e-9), -1, 1))))
        e = np.array(errs)
        out[gd] = e
        print(f"{gd:>6}{len(e):>4}{np.median(e):>9.2f}{e.mean():>8.2f}"
              f"{np.mean(e < 1) * 100:>5.0f}%{np.mean(e > 10) * 100:>6.0f}%"
              f"{np.mean(verts):>10.2f}{np.mean(defs):>11.2f}{np.mean(dirs):>9.1f}")
    venv.close()

    desc = np.concatenate([out[g] for g in ANGLES if g < 0])
    climb = np.concatenate([out[g] for g in ANGLES if g > 0])
    steep = np.concatenate([out[g] for g in (-40, -30)])
    shallow = np.concatenate([out[g] for g in (-20, -10)])
    print(f"\ndescents  n={len(desc):>3} median {np.median(desc):>6.2f}   "
          f"climbs n={len(climb):>3} median {np.median(climb):>6.2f}")
    print(f"  steep (-40,-30) median {np.median(steep):>6.2f}   "
          f"shallow (-20,-10) median {np.median(shallow):>6.2f}")
    print("  thrust-floor hypothesis predicts steep >> shallow; a flat descent profile "
          "refutes it as the sole cause")


if __name__ == "__main__":
    main()
