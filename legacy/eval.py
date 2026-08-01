"""Evaluate a trained velocity-tracking policy.

Reports mean steady-state tracking error over N random targets and (optionally)
renders in the PyBullet GUI and saves a velocity-vs-target plot.

Examples
--------
    python eval.py --episodes 20
    python eval.py --gui --episodes 3
    python eval.py --plot track.png
"""
import argparse
import os
import json
import numpy as np

from stable_baselines3 import PPO, SAC
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize, VecFrameStack

from rate_vel_aviary import RateVelAviary
from progress_callback import unwrap_base


def load(out_dir, gui):
    algo = SAC if os.path.exists(os.path.join(out_dir, "sac_ratevel_final.zip")) else PPO
    model_path = (os.path.join(out_dir, "best", "best_model.zip")
                  if os.path.exists(os.path.join(out_dir, "best", "best_model.zip"))
                  else os.path.join(out_dir, f"{algo.__name__.lower()}_ratevel_final.zip"))
    cfg = os.path.join(out_dir, "config.json")
    n_stack = json.load(open(cfg)).get("n_stack", 1) if os.path.exists(cfg) else 1
    venv = DummyVecEnv([lambda: RateVelAviary(gui=gui, episode_len_sec=8.0, max_speed=20.0)])
    if n_stack > 1:                                    # stack INSIDE, matching training
        venv = VecFrameStack(venv, n_stack=n_stack)
    venv = VecNormalize.load(os.path.join(out_dir, "vecnormalize.pkl"), venv)
    venv.training = False
    venv.norm_reward = False
    model = algo.load(model_path)
    print(f"[INFO] loaded {model_path} (n_stack={n_stack})")
    return model, venv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=str, default="results")
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--gui", action="store_true")
    ap.add_argument("--plot", type=str, default=None, help="save vel-vs-target plot for episode 0")
    args = ap.parse_args()

    model, venv = load(args.out_dir, args.gui)
    base = unwrap_base(venv)      # underlying RateVelAviary (for info + timestep)

    final_errs, mean_errs = [], []
    trace = []                    # (t, vel(3), target(3)) for episode 0
    for ep in range(args.episodes):
        obs = venv.reset()
        target = base.target_vel.copy()
        errs, t = [], 0.0
        done = False
        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, _, dones, infos = venv.step(action)
            done = bool(dones[0])
            errs.append(infos[0]["vel_error"])
            if ep == 0:
                trace.append((t, base.vel[0].copy(), target.copy()))
                t += base.CTRL_TIMESTEP
        errs = np.array(errs)
        # steady state = last 2 s of the episode
        ss = errs[-int(2.0 / base.CTRL_TIMESTEP):]
        final_errs.append(ss.mean()); mean_errs.append(errs.mean())
        print(f"  ep {ep:2d}  |target|={np.linalg.norm(target):5.2f}  "
              f"mean_err={errs.mean():5.2f}  steady_err={ss.mean():5.2f} m/s")

    print(f"\n[RESULT] over {args.episodes} eps: "
          f"mean err {np.mean(mean_errs):.3f} m/s | steady-state err {np.mean(final_errs):.3f} m/s")

    if args.plot and trace:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        ts = np.array([x[0] for x in trace])
        vel = np.array([x[1] for x in trace])
        tgt = np.array([x[2] for x in trace])
        fig, axs = plt.subplots(3, 1, figsize=(8, 7), sharex=True)
        for i, lab in enumerate(["vx", "vy", "vz"]):
            axs[i].plot(ts, vel[:, i], label=f"{lab} actual")
            axs[i].axhline(tgt[0, i], ls="--", color="k", label=f"{lab} target")
            axs[i].set_ylabel("m/s"); axs[i].legend(loc="right"); axs[i].grid(alpha=0.3)
        axs[-1].set_xlabel("time (s)")
        fig.suptitle("Velocity tracking (episode 0)")
        fig.tight_layout(); fig.savefig(args.plot, dpi=120)
        print(f"[INFO] saved plot to {args.plot}")

    venv.close()


if __name__ == "__main__":
    main()
