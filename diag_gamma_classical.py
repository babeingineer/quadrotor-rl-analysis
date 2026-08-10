"""Does the CLASSICAL cascade hold commanded descents, where the RL policies cannot?

Trial 75 established that RL policies fail descents by up to 4.2x at matched speed, and that it
is a stabilization failure (they depart a descent even when started in one). This asks whether
the deficit is a property of the AIRCRAFT or of the LEARNED POLICIES, using the same stratified
gamma sweep on classical_baseline.py.

  * classical holds descents -> the plant is fine; the RL policies simply never learned it, and
    a PID teacher possesses exactly the missing skill (motivates BC-initialised RL)
  * classical also fails -> descents are hard for any controller of this class, and a teacher
    has nothing to teach

Same protocol as diag_gamma_sweep.py: target direction forced, n per angle, steady state = last
3 s, full DR and wind.

    python diag_gamma_classical.py --lo 25 --hi 34 --per-angle 20
"""
import argparse

import numpy as np

from classical_baseline import ClassicalController
from rate_vel_aviary import RateVelAviary

ANGLES = [-40, -30, -20, -10, 0, 10, 20, 30, 40]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lo", type=float, default=25.0)
    ap.add_argument("--hi", type=float, default=34.0)
    ap.add_argument("--per-angle", type=int, default=20)
    ap.add_argument("--ep-len", type=float, default=8.0)
    ap.add_argument("--kp", type=float, default=1.2)
    ap.add_argument("--ki", type=float, default=0.4)
    ap.add_argument("--katt", type=float, default=4.0)
    ap.add_argument("--kfin", type=float, default=0.0)
    # Trial 21's winning config is kp=0.6 ki=0.15 katt=1.8 ff=0.2 — the module defaults
    # (kp=1.2 ki=0.4 katt=4.0 ff=1.0) are the UNTUNED ones and diverge under full DR.
    ap.add_argument("--ff", type=float, default=1.0,
                    help="observer feedforward scale; <1 damps the est-attitude coupling loop")
    ap.add_argument("--v0", type=float, default=0.0, help="gain-scheduling speed (0 = fixed)")
    ap.add_argument("--int-clamp", type=float, default=8.0)
    args = ap.parse_args()

    env = RateVelAviary(use_xwing_aero=True, randomize_init=False, wind_max=15.0,
                        speed_min=args.lo, max_speed=args.hi, yaw_bias_max=0.3,
                        episode_len_sec=args.ep_len, kp_rate=(40, 40, 25), ki_rate=(10, 10, 5))
    ctl = ClassicalController(env, kp=args.kp, ki=args.ki, katt=args.katt, kfin=args.kfin,
                              ff=args.ff, v0=args.v0, int_clamp=args.int_clamp)
    dt = env.CTRL_TIMESTEP
    N = int(args.ep_len / dt)
    k0 = N - int(3.0 / dt)
    print(f"classical cascade  band {args.lo:g}-{args.hi:g}  n={args.per_angle}/angle")
    print(f"\n{'gamma':>6}{'n':>4}{'median':>9}{'mean':>8}{'%<1':>6}{'%>10':>7}"
          f"{'vert err':>10}{'speed def':>11}")
    print("-" * 61)
    out = {}
    for gd in ANGLES:
        g = np.radians(gd)
        errs, verts, defs = [], [], []
        for i in range(args.per_angle):
            env.reset(seed=30000 + i)
            ctl.reset()
            rng = np.random.default_rng(30000 + i)
            psi = rng.uniform(0, 2 * np.pi)
            V = float(rng.uniform(args.lo, args.hi))
            tv = V * np.array([np.cos(g) * np.cos(psi), np.cos(g) * np.sin(psi), np.sin(g)])
            env.target_vel = tv.copy()
            vels = []
            for k in range(N):
                a = ctl.act(dt)
                _, _, term, trunc, _ = env.step(a)
                env.target_vel = tv.copy()
                if k >= k0:
                    vels.append(env.vel[0].copy())
                if term or trunc:
                    break
            if not vels:
                continue
            vm = np.mean(vels, axis=0)
            errs.append(float(np.linalg.norm(vm - tv)))
            verts.append(float(vm[2] - tv[2]))
            defs.append(V - float(np.linalg.norm(vm)))
        e = np.array(errs)
        out[gd] = e
        print(f"{gd:>6}{len(e):>4}{np.median(e):>9.2f}{e.mean():>8.2f}"
              f"{np.mean(e < 1) * 100:>5.0f}%{np.mean(e > 10) * 100:>6.0f}%"
              f"{np.mean(verts):>10.2f}{np.mean(defs):>11.2f}")
    env.close()
    d = np.concatenate([out[g] for g in ANGLES if g < 0])
    c = np.concatenate([out[g] for g in ANGLES if g > 0])
    print(f"\ndescents n={len(d)} median {np.median(d):.2f}   "
          f"climbs n={len(c)} median {np.median(c):.2f}   "
          f"ratio {np.median(d) / max(np.median(c), 1e-9):.2f}x")
    print("RL specialist on the same band/protocol: descents 10.16 vs climbs 2.44 = 4.2x")


if __name__ == "__main__":
    main()
