"""Measure the supervisory recovery switch on ONE band champion, both columns in one run:

  * recovery  — episodes started in failure states (tough_init), scored like dive_recovery_test
  * precision — ordinary episodes, scored like eval_velyaw (steady-state over the final 3 s)

Both must be reported together: a detector that recovers well by firing constantly buys
recovery with precision. Firing rate on nominal flights is the number that exposes that.

    python eval_recovery_switch.py --nominal results_velyaw_xw35b --upsets 60 --nominal-eps 150
"""
import argparse

import numpy as np

from recovery_switch import (ARM_SEC, GENERALIST, STAY_SEC, build_env, check_compatible,
                             load_policy, run_episode)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nominal", default="results_velyaw_xw35b", help="band champion")
    ap.add_argument("--recovery", default=GENERALIST, help="full-envelope generalist")
    ap.add_argument("--band", type=str, default=None,
                    help="lo,hi commanded-speed range (default: the champion's own range)")
    ap.add_argument("--upsets", type=int, default=60)
    ap.add_argument("--nominal-eps", type=int, default=150)
    ap.add_argument("--ep-len", type=float, default=10.0)
    ap.add_argument("--arm", type=float, default=ARM_SEC,
                    help="seconds of sustained upset to engage (calibrated default)")
    ap.add_argument("--stay", type=float, default=STAY_SEC, help="minimum seconds engaged")
    ap.add_argument("--baseline", action="store_true",
                    help="also run the champion alone, for the same seeds")
    args = ap.parse_args()

    nom, rec = load_policy(args.nominal), load_policy(args.recovery)
    check_compatible(nom, rec)
    if args.band:
        lo, hi = (float(x) for x in args.band.split(","))
    else:
        lo = float(nom["cfg"].get("speed_min", 0.0))
        hi = float(nom["cfg"].get("max_speed", 25.0))
    print(f"switch: {args.nominal} (band {lo:g}-{hi:g}) <- {args.recovery} on upset")
    print(f"dwell: arm {args.arm:g}s / stay {args.stay:g}s")

    def sweep(upset, n, seed0, solo):
        env = build_env(nom["cfg"], args.ep_len, lo, hi, upset=upset)
        out = []
        for i in range(n):
            out.append(run_episode(env, nom, nom if solo else rec, seed0 + i, lo, hi,
                                   args.ep_len, start_in_recovery=(upset and not solo),
                                   arm_sec=args.arm, stay_sec=args.stay))
        env.close()
        return out

    for solo in ([False, True] if args.baseline else [False]):
        tag = "champion alone" if solo else "SWITCH"
        up = sweep(True, args.upsets, 1000, solo)
        f = np.array([r["final_err"] for r in up])
        nm = sweep(False, args.nominal_eps, 5000, solo)
        ok = [r for r in nm if not r["crashed"]]
        e = np.array([r["vel_err"] for r in ok])
        boots = [np.median(np.random.default_rng(i).choice(e, len(e))) for i in range(200)]
        print(f"\n=== {tag} ===")
        print(f"  recovery  n={len(f):>3}  recovered(<8) {np.mean(f < 8) * 100:3.0f}%  "
              f"partial(8-15) {np.mean((f >= 8) & (f < 15)) * 100:3.0f}%  "
              f"median final {np.median(f):5.1f}")
        print(f"  precision n={len(ok):>3}  median {np.median(e):4.2f} "
              f"[CI {np.percentile(boots, 2.5):4.2f}-{np.percentile(boots, 97.5):4.2f}]  "
              f"<1 {np.mean(e < 1) * 100:3.0f}%  p90 {np.percentile(e, 90):5.2f}  "
              f"crash {(1 - len(ok) / len(nm)) * 100:.1f}%")
        if not solo:
            print(f"  spurious  fired in {np.mean([r['fired'] for r in nm]) * 100:3.0f}% of "
                  f"nominal episodes  {np.mean([r['switches'] for r in nm]):.1f} switches/ep  "
                  f"{np.mean([r['frac_rec'] for r in nm]) * 100:.0f}% of steps in generalist")


if __name__ == "__main__":
    main()
