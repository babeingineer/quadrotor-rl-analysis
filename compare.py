"""Head-to-head comparison of the PPO and SAC policies on RateVelAviary.

Produces:
  * comparison_curves.png  — eval-return learning curves (PPO vs SAC) vs timesteps
  * comparison_summary.png — bar chart of aggregate metrics
  * prints a metrics table (evaluated on the SAME random scenarios for both)

Both are evaluated with an identical protocol: N scenarios generated from a fixed
seed, with per-episode mass/wind/target drawn identically for each model.
"""
import argparse
import os
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from stable_baselines3 import PPO, SAC
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize, VecFrameStack
from rate_vel_aviary import RateVelAviary
from progress_callback import unwrap_base

ALGOS = {"PPO": PPO, "SAC": SAC}


def load(out_dir, algo):
    for name in ("best/best_model.zip", f"{algo.lower()}_ratevel_final.zip",
                 "ppo_ratevel_final.zip"):
        pth = os.path.join(out_dir, name)
        if os.path.exists(pth):
            model = ALGOS[algo].load(pth)
            break
    else:
        raise FileNotFoundError(f"no model in {out_dir}")
    cfg_path = os.path.join(out_dir, "config.json")
    n_stack = json.load(open(cfg_path)).get("n_stack", 1) if os.path.exists(cfg_path) else 1
    venv = DummyVecEnv([lambda: RateVelAviary(episode_len_sec=8.0, max_speed=20.0)])
    if n_stack > 1:                                    # stack INSIDE, matching training
        venv = VecFrameStack(venv, n_stack=n_stack)
    venv = VecNormalize.load(os.path.join(out_dir, "vecnormalize.pkl"), venv)
    venv.training = False; venv.norm_reward = False
    return model, venv


def evaluate(model, venv, seeds):
    base = unwrap_base(venv)
    rows = []
    for sd in seeds:
        venv.seed(int(sd)); obs = venv.reset()
        tgt = base.target_vel.copy(); spd = float(np.linalg.norm(tgt))
        errs, n, done = [], 0, False
        while not done:
            a, _ = model.predict(obs, deterministic=True)
            obs, _, d, inf = venv.step(a); done = bool(d[0])
            errs.append(inf[0]["vel_error"]); n += 1
        ss = float(np.mean(errs[-max(1, len(errs) // 4):]))
        crashed = n < 400
        rows.append(dict(spd=spd, steady=ss, crashed=crashed, length=n))
    return rows


def summarize(rows):
    ss = np.array([r["steady"] for r in rows])
    crashed = np.array([r["crashed"] for r in rows])
    spd = np.array([r["spd"] for r in rows])
    lo = spd <= 15.0
    return dict(
        n=len(rows),
        crash_rate=float(crashed.mean()),
        mean_steady=float(ss.mean()),
        median_steady=float(np.median(ss)),
        mean_steady_no_crash=float(ss[~crashed].mean()) if (~crashed).any() else float("nan"),
        mean_steady_le15=float(ss[lo].mean()) if lo.any() else float("nan"),
        crash_rate_gt15=float(crashed[~lo].mean()) if (~lo).any() else float("nan"),
    )


def curve(out_dir):
    d = np.load(os.path.join(out_dir, "eval", "evaluations.npz"))
    return d["timesteps"], d["results"].mean(axis=1), d["results"].std(axis=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ppo-dir", default="results")
    ap.add_argument("--sac-dir", default="results_sac")
    ap.add_argument("--episodes", type=int, default=50)
    args = ap.parse_args()

    seeds = np.arange(1000, 1000 + args.episodes)
    results = {}
    for algo, d in (("PPO", args.ppo_dir), ("SAC", args.sac_dir)):
        model, venv = load(d, algo)
        rows = evaluate(model, venv, seeds)
        results[algo] = summarize(rows)
        venv.close()

    # ---- table ----
    keys = [("n", "episodes"), ("mean_steady", "mean steady err (m/s)"),
            ("median_steady", "median steady err (m/s)"),
            ("mean_steady_le15", "mean steady err, tgt<=15 (m/s)"),
            ("mean_steady_no_crash", "mean steady err, non-crash (m/s)"),
            ("crash_rate", "crash rate (all)"),
            ("crash_rate_gt15", "crash rate, tgt>15")]
    print(f"\n{'metric':<38}{'PPO':>12}{'SAC':>12}")
    print("-" * 62)
    for k, lab in keys:
        pv, sv = results["PPO"][k], results["SAC"][k]
        fmt = (lambda x: f"{x:>12.0f}") if k == "n" else (lambda x: f"{x:>12.3f}")
        print(f"{lab:<38}{fmt(pv)}{fmt(sv)}")

    # ---- learning-curve overlay ----
    fig, ax = plt.subplots(figsize=(9, 5))
    for algo, d, c in (("PPO", args.ppo_dir, "C0"), ("SAC", args.sac_dir, "C1")):
        try:
            t, m, s = curve(d)
            ax.plot(t, m, color=c, marker="o", ms=3, label=algo)
            ax.fill_between(t, m - s, m + s, color=c, alpha=0.15)
        except Exception as e:
            print(f"[warn] no curve for {algo}: {e}")
    ax.set_xlabel("environment timesteps"); ax.set_ylabel("eval episode return")
    ax.set_title("PPO vs SAC — learning curves (RateVelAviary velocity tracking)")
    ax.grid(alpha=0.3); ax.legend()
    fig.tight_layout(); fig.savefig("comparison_curves.png", dpi=130)
    print("\n[saved] comparison_curves.png")

    # ---- summary bars ----
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.5))
    bark = [("mean_steady_le15", "mean steady err\n(tgt<=15 m/s)"),
            ("mean_steady_no_crash", "mean steady err\n(non-crash)")]
    x = np.arange(2)
    axs[0].bar(x - 0.2, [results["PPO"][k] for k, _ in bark], 0.4, label="PPO", color="C0")
    axs[0].bar(x + 0.2, [results["SAC"][k] for k, _ in bark], 0.4, label="SAC", color="C1")
    axs[0].set_xticks(x); axs[0].set_xticklabels([l for _, l in bark])
    axs[0].set_ylabel("m/s"); axs[0].set_title("Tracking error (lower better)"); axs[0].legend()
    ck = [("crash_rate", "all targets"), ("crash_rate_gt15", "targets >15 m/s")]
    axs[1].bar(x - 0.2, [results["PPO"][k] for k, _ in ck], 0.4, label="PPO", color="C0")
    axs[1].bar(x + 0.2, [results["SAC"][k] for k, _ in ck], 0.4, label="SAC", color="C1")
    axs[1].set_xticks(x); axs[1].set_xticklabels([l for _, l in ck])
    axs[1].set_ylabel("fraction"); axs[1].set_title("Crash rate (lower better)"); axs[1].legend()
    fig.tight_layout(); fig.savefig("comparison_summary.png", dpi=130)
    print("[saved] comparison_summary.png")


if __name__ == "__main__":
    main()
