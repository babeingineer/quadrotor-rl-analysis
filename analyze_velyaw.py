"""Post-training analysis for a velyaw policy — run automatically after training:
  1. physical eval: velocity error by speed band + heading error (deg) + crash rate
  2. DIVE-RECOVERY test: every episode starts in a failure state (tough init); measures
     whether the policy arrests the dive and returns to tracking
  3. behavior traces: a few episodes printed step-by-step for qualitative inspection

    python analyze_velyaw.py --dir results_velyaw_xw7
"""
import argparse
import json
import os
import numpy as np
import pybullet as p
from eval_velyaw import load, evaluate, report


def dive_recovery_test(D, n=60, ep_len=10.0, **checkpoint_kwargs):
    """All episodes start mid-dive / mid-botched-transition (tough_init_frac=1)."""
    model, venv, base = load(D, ep_len=ep_len, randomize_init=True,
                             tough_init_frac=1.0, **checkpoint_kwargs)
    dt = base.CTRL_TIMESTEP; N = int(ep_len / dt)
    recovered = partial = 0; final_errs = []
    for i in range(n):
        venv.seed(3000 + i)
        obs = venv.reset()
        model.reset()
        errs = []
        for k in range(N):
            a, _ = model.predict(obs, deterministic=True)
            obs, _, done, infos = venv.step(a)
            if k >= N - int(2.0 / dt):
                errs.append(infos[0]["vel_error"])
            if done[0]:
                break
        fe = float(np.mean(errs)) if errs else np.nan
        final_errs.append(fe)
        if fe < 8.0:
            recovered += 1
        elif fe < 15.0:
            partial += 1
    venv.close()
    print(f"\n=== DIVE-RECOVERY TEST ({n} episodes, all starting in failure states) ===")
    print(f"  recovered (final-2s vel err < 8 m/s):  {recovered}/{n} = {100*recovered/n:.0f}%")
    print(f"  partial   (8-15 m/s):                  {partial}/{n} = {100*partial/n:.0f}%")
    print(f"  median final err: {np.median(final_errs):.1f} m/s   "
          f"mean: {np.mean(final_errs):.1f} m/s")
    return recovered / n


def traces(D, seeds=(1005, 1012, 1020), ep_len=10.0, **checkpoint_kwargs):
    model, venv, base = load(D, ep_len=ep_len, **checkpoint_kwargs)
    dt = base.CTRL_TIMESTEP
    for seed in seeds:
        venv.seed(seed); obs = venv.reset(); model.reset()
        tgt = base.target_vel.copy()
        print(f"\n--- trace seed {seed}: target {tgt.round(1)} (|v|={np.linalg.norm(tgt):.1f}), "
              f"wind {base.wind.round(1)} ---")
        for k in range(int(ep_len / dt)):
            a, _ = model.predict(obs, deterministic=True)
            obs, _, done, infos = venv.step(a)
            if k % 100 == 0:
                v = base.vel[0]
                R = np.array(p.getMatrixFromQuaternion(base.quat[0])).reshape(3, 3)
                tilt = np.degrees(np.arccos(np.clip(R[2, 2], -1, 1)))
                aa = np.asarray(a).ravel()
                print(f"  t={k*dt:4.1f} |v|={np.linalg.norm(v):5.1f} vz={v[2]:6.1f} "
                      f"tilt={tilt:4.0f} verr={infos[0]['vel_error']:5.1f} "
                      f"yawerr={np.degrees(infos[0]['yaw_error']):+6.1f} "
                      f"fins=({np.degrees(base.fin_angles[0]):+5.1f},"
                      f"{np.degrees(base.fin_angles[1]):+5.1f}) thr={aa[2]:+.2f}")
    venv.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="results_velyaw_xw7")
    ap.add_argument("--episodes", type=int, default=120)
    ap.add_argument("--ep-len", type=float, default=None,
                    help="eval episode length (s); default = the trained episode_len from "
                         "config.json, so slow-settling policies are not clipped early")
    ap.add_argument("--checkpoint", choices=("auto", "best", "final", "legacy-best"),
                    default="auto")
    ap.add_argument("--model-file", default=None)
    ap.add_argument("--vecnormalize-file", default=None)
    args = ap.parse_args()
    cfg = json.load(open(os.path.join(args.dir, "config.json")))
    ep_len = args.ep_len if args.ep_len is not None else float(cfg.get("episode_len", 10.0))
    checkpoint_kwargs = dict(checkpoint=args.checkpoint, model_file=args.model_file,
                             vecnormalize_file=args.vecnormalize_file)
    print(f"################ ANALYSIS: {args.dir} (ep_len {ep_len:g}s) ################")
    print(f"\n=== PHYSICAL EVAL (level start, full wind, {ep_len:g}s episodes) ===")
    report(evaluate(args.dir, n=args.episodes, ep_len=ep_len, **checkpoint_kwargs))
    dive_recovery_test(args.dir, ep_len=ep_len, **checkpoint_kwargs)
    traces(args.dir, ep_len=ep_len, **checkpoint_kwargs)
    print("\n[ANALYSIS DONE]")
