"""What separates a SUCCESSFUL 25-34 m/s episode from a failed one?

The vhigh band's error is bimodal (p25 = 2.30, p75 = 13.18) and essentially uncorrelated with
commanded speed (+0.09), so the 5.73 median is a mixture of tracking and failing, not uniform
mediocrity — and it is not a thrust/speed ceiling. This records the per-episode conditions
(climb angle, wind magnitude and direction, DR draw) alongside the outcome, then reports what
actually separates the two modes.

Also decomposes the residual: a SPEED deficit (can't go fast enough), a DIRECTION error (flying
the wrong way), or a VERTICAL error (sinking) imply different fixes.

    python diag_vhigh_failure.py --dir results_velyaw_xw55a --episodes 150
"""
import argparse

import numpy as np

from eval_velyaw import load


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="results_velyaw_xw55a")
    ap.add_argument("--episodes", type=int, default=150)
    ap.add_argument("--ep-len", type=float, default=8.0)
    ap.add_argument("--lo", type=float, default=25.0)
    ap.add_argument("--hi", type=float, default=34.0)
    args = ap.parse_args()

    model, venv, base = load(args.dir, args.ep_len, speed_min=args.lo, max_speed=args.hi)
    dt = base.CTRL_TIMESTEP
    N = int(args.ep_len / dt)
    k0 = N - int(3.0 / dt)
    rows = []
    for i in range(args.episodes):
        venv.seed(20000 + i)
        obs = venv.reset()
        model.reset()
        tv = base.target_vel.copy()
        V = float(np.linalg.norm(tv))
        gamma = np.degrees(np.arcsin(np.clip(tv[2] / max(V, 1e-6), -1, 1)))
        wind = base.wind.copy()
        wmag = float(np.linalg.norm(wind))
        # + = headwind component opposing the target direction
        head = float(-wind @ (tv / max(V, 1e-6)))
        mass, tau = float(base.M), float(base.motor_tau)
        aero = base.aero_rand.copy() if hasattr(base, "aero_rand") else np.ones(1)
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
        err = float(np.linalg.norm(vm - tv))
        speed_def = V - float(np.linalg.norm(vm))          # + = too slow
        vert = float(vm[2] - tv[2])                        # - = sinking vs command
        # horizontal direction error (deg) between achieved and commanded horizontal velocity
        h1, h2 = vm[:2], tv[:2]
        dir_err = np.degrees(np.arccos(np.clip(
            (h1 @ h2) / max(np.linalg.norm(h1) * np.linalg.norm(h2), 1e-9), -1, 1)))
        rows.append((err, V, gamma, wmag, head, speed_def, vert, dir_err, mass, tau,
                     float(np.mean(np.abs(aero - 1.0)))))
    venv.close()

    a = np.array(rows)
    err = a[:, 0]
    good, bad = err < 3.0, err > 10.0
    names = ["cmd speed V", "climb angle gamma", "wind |w|", "headwind comp",
             "speed deficit", "vertical err", "dir err (deg)", "mass", "motor tau", "aero dev"]
    print(f"{args.dir}: n={len(a)}  median err {np.median(err):.2f}  "
          f"good(<3) {good.sum()}  bad(>10) {bad.sum()}")
    print(f"\n{'feature':<20}{'GOOD mean':>11}{'BAD mean':>11}{'diff':>9}{'corr w/ err':>13}")
    print("-" * 66)
    for j, nm in enumerate(names, start=1):
        g, b = a[good, j].mean(), a[bad, j].mean()
        c = np.corrcoef(a[:, j], err)[0, 1]
        print(f"{nm:<20}{g:>11.2f}{b:>11.2f}{b - g:>9.2f}{c:>13:+.3f}"
              if False else f"{nm:<20}{g:>11.2f}{b:>11.2f}{b - g:>9.2f}{c:>+13.3f}")

    print("\nRESIDUAL DECOMPOSITION on failures (what the error actually IS):")
    for tag, m in (("good (<3)", good), ("bad (>10)", bad)):
        if m.sum():
            print(f"  {tag:<11} speed deficit {a[m, 5].mean():>7.2f}   vertical "
                  f"{a[m, 6].mean():>7.2f}   direction {a[m, 7].mean():>6.1f} deg")
    print("\nclimb-angle breakdown (gamma = commanded flight-path angle):")
    for lo, hi in ((-45, -20), (-20, -5), (-5, 5), (5, 20), (20, 45)):
        m = (a[:, 2] >= lo) & (a[:, 2] < hi)
        if m.sum() > 2:
            print(f"  gamma {lo:>4} to {hi:>3}: n={m.sum():>3}  median err {np.median(err[m]):>6.2f}"
                  f"   frac>10 {np.mean(err[m] > 10) * 100:>4.0f}%")


if __name__ == "__main__":
    main()
