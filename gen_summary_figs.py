"""Generate figures for SUMMARY.md (saved to docs/)."""
import os, json
import numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from stable_baselines3 import PPO, SAC
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from rate_vel_aviary import RateVelAviary
from progress_callback import unwrap_base
from compare_tasks import run as pos_run    # position-control driver (vel+loop or position policy)

OUT = "docs"; os.makedirs(OUT, exist_ok=True)
VEL, POS = "results_obs", "results_pos3d"
START = np.array([0, 0, 2.0])


def load(dirn, ep=30.0, gui=False):
    cfg = json.load(open(f"{dirn}/config.json"))
    algo = SAC if os.path.exists(f"{dirn}/sac_ratevel_final.zip") else PPO
    venv = DummyVecEnv([lambda: RateVelAviary(task=cfg.get("task", "velocity"), episode_len_sec=ep,
                        max_speed=20, pos_range=cfg.get("pos_range", 30), speed_cap=cfg.get("speed_cap", 18))])
    venv = VecNormalize.load(f"{dirn}/vecnormalize.pkl", venv); venv.training = False; venv.norm_reward = False
    mp = f"{dirn}/best/best_model.zip"
    return algo.load(mp), venv, unwrap_base(venv)


# ---------- 1. velocity tracking (velocity policy) ----------
def fig_velocity():
    model, venv, base = load(VEL)
    venv.seed(1); venv.reset(); base.wind = np.array([8.0, 0, 0]); base.MASS_RANGE = (10, 10)
    tgt = np.array([12.0, -6.0, 3.0]); dt = base.CTRL_TIMESTEP
    ts, vs = [], []; t = 0.0
    for _ in range(300):
        base.target_vel = tgt
        obs = venv.normalize_obs(base._computeObs()[None]); a, _ = model.predict(obs, deterministic=True); venv.step(a)
        vs.append(base.vel[0].copy()); ts.append(t); t += dt
    venv.close(); vs = np.array(vs); ts = np.array(ts)
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for i, l in enumerate(["vx", "vy", "vz"]):
        ax.plot(ts, vs[:, i], color=f"C{i}", label=f"{l}")
        ax.axhline(tgt[i], ls="--", color=f"C{i}", alpha=0.5)
    ax.set_xlabel("time (s)"); ax.set_ylabel("velocity (m/s)"); ax.grid(alpha=.3); ax.legend(loc="right")
    ax.set_title("Velocity tracking (PPO): target = (12, -6, 3) m/s, 8 m/s wind\n(dashed = target)")
    fig.tight_layout(); fig.savefig(f"{OUT}/fig_velocity_track.png", dpi=120); plt.close(fig)
    print("fig_velocity_track.png")


# ---------- 2. hover: position policy vs velocity+loop ----------
def fig_hover():
    N = int(10 / 0.02)
    fig, axs = plt.subplots(1, 2, figsize=(12, 4.2), sharey=True)
    for ax, (wind, wl) in zip(axs, [((0, 0, 0), "calm"), ((15, 0, 0), "15 m/s wind")]):
        for lab, d, c in [("velocity+loop", VEL, "C0"), ("position policy", POS, "C1")]:
            p, g, dt = pos_run(d, lambda t: START, N, wind=wind)
            ax.plot(np.arange(len(p)) * dt, np.linalg.norm(p - g, axis=1), color=c, label=lab)
        ax.set_xlabel("time (s)"); ax.set_title(f"Hover hold ({wl})"); ax.grid(alpha=.3); ax.legend()
    axs[0].set_ylabel("position error (m)")
    fig.suptitle("Station-keeping: hold at start point"); fig.tight_layout()
    fig.savefig(f"{OUT}/fig_hover.png", dpi=120); plt.close(fig)
    print("fig_hover.png")


# ---------- 3. trajectory (circle) ----------
def fig_trajectory():
    N = int(16 / 0.02); c = np.array([0, 0, 2.0]); r = 3.0; w = 2 * np.pi / 8
    circle = lambda t: c + np.array([r * np.cos(w * t) - r, r * np.sin(w * t), 0])
    fig, ax = plt.subplots(figsize=(6.2, 6))
    ref = None
    for lab, d, c2 in [("velocity+loop", VEL, "C0"), ("position policy", POS, "C1")]:
        p, g, dt = pos_run(d, circle, N)
        if ref is None:
            ax.plot(g[:, 0], g[:, 1], "k--", lw=2, label="reference"); ref = g
        ax.plot(p[:, 0], p[:, 1], color=c2, label=lab, alpha=0.9)
    ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)"); ax.axis("equal"); ax.grid(alpha=.3); ax.legend()
    ax.set_title("Trajectory tracking: 3 m circle, 8 s period")
    fig.tight_layout(); fig.savefig(f"{OUT}/fig_trajectory.png", dpi=120); plt.close(fig)
    print("fig_trajectory.png")


# ---------- 4. step response ----------
def fig_step():
    N = int(8 / 0.02); goal = lambda t: np.array([4.0, 0, 2.0])
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for lab, d, c in [("velocity+loop", VEL, "C0"), ("position policy", POS, "C1")]:
        p, g, dt = pos_run(d, goal, N)
        ax.plot(np.arange(len(p)) * dt, p[:, 0], color=c, label=lab)
    ax.axhline(4.0, ls="--", color="k", label="target"); ax.grid(alpha=.3); ax.legend()
    ax.set_xlabel("time (s)"); ax.set_ylabel("x (m)"); ax.set_title("Step response: 4 m step in x")
    fig.tight_layout(); fig.savefig(f"{OUT}/fig_step.png", dpi=120); plt.close(fig)
    print("fig_step.png")


# ---------- 5. position learning curve (0->12M, concatenated) ----------
def fig_pos_training():
    fig, ax = plt.subplots(figsize=(8, 4.2))
    T, R = [], []
    for d in ["results_pos3", "results_pos3b", "results_pos3c", "results_pos3d"]:
        p = f"{d}/eval/evaluations.npz"
        if os.path.exists(p):
            z = np.load(p); T += list(z["timesteps"]); R += list(z["results"].mean(1))
    idx = np.argsort(T); T = np.array(T)[idx]; R = np.array(R)[idx]
    ax.plot(T / 1e6, R, color="C1"); ax.grid(alpha=.3)
    ax.set_xlabel("environment steps (millions)"); ax.set_ylabel("eval return")
    ax.set_title("Position-PPO learning curve (0 -> 12M, pure reward)")
    fig.tight_layout(); fig.savefig(f"{OUT}/fig_pos_training.png", dpi=120); plt.close(fig)
    print("fig_pos_training.png")


# ---------- 6. PPO vs SAC (velocity task) ----------
def fig_ppo_sac():
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for lab, d, c in [("PPO (velocity)", "results_obs", "C0"), ("SAC tuned (velocity)", "results_sac_tuned", "C1")]:
        p = f"{d}/eval/evaluations.npz"
        if os.path.exists(p):
            z = np.load(p); r = z["results"].mean(1)
            ax.plot(z["timesteps"] / 1e6, r, color=c, marker="o", ms=2, label=lab)
    ax.set_xlabel("environment steps (millions)"); ax.set_ylabel("eval return")
    ax.set_title("PPO vs tuned SAC (velocity task)"); ax.grid(alpha=.3); ax.legend()
    fig.tight_layout(); fig.savefig(f"{OUT}/fig_ppo_vs_sac.png", dpi=120); plt.close(fig)
    print("fig_ppo_vs_sac.png")


if __name__ == "__main__":
    fig_velocity(); fig_hover(); fig_trajectory(); fig_step(); fig_pos_training(); fig_ppo_sac()
    print("done ->", OUT)
