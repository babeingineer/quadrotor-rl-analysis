"""Run hover-hold + circular-path inference on EVERY runnable trained model and
save comparison figures to docs/.

Only the 9 models whose obs layout matches the current 29-dim direct-sensing env
are runnable. The 3 earliest (results_sac 22-dim, results_fs / results_sac_fs
88-dim=22x4 frame-stack) predate RPM+wind sensing and cannot produce a matching
obs -- they are documented with historical velocity numbers instead.

Velocity policies are driven as position controllers via an outer P-loop
(v_cmd = v_ff + Kp*(goal-pos), clipped); position policies are handed the goal
directly (carrot). Same tasks, same seeds for a fair comparison.
"""
import os, json
import numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from stable_baselines3 import PPO, SAC
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from rate_vel_aviary import RateVelAviary
from progress_callback import unwrap_base

OUT = "docs"; os.makedirs(OUT, exist_ok=True)
VMAX, KP = 18.0, 1.5          # outer position-loop clamp + gain (match compare_tasks)
START = np.array([0, 0, 2.0])

# runnable models (label, dir) -- all 29-dim, n_stack=1
VEL = [("PPO T6 (obs) [FINAL]", "results_obs"),
       ("SAC T7 (obs)",        "results_sac_obs"),
       ("SAC T8 (tuned)",      "results_sac_tuned")]
POS = [("T11 pos (Gauss 1.5)", "results_pos"),
       ("T12 pos2 (exp 0.3)",  "results_pos2"),
       ("T13 pos3 (exp 1.0 3M)", "results_pos3"),
       ("T14 pos3b (6M)",      "results_pos3b"),
       ("T15 pos3c (9M)",      "results_pos3c"),
       ("T16 pos3d (12M) [FINAL]", "results_pos3d")]


def load(out_dir, ep_len=60.0):
    cfg = json.load(open(os.path.join(out_dir, "config.json")))
    task = cfg.get("task", "velocity")
    algo = SAC if os.path.exists(os.path.join(out_dir, "sac_ratevel_final.zip")) else PPO
    pr, sc = cfg.get("pos_range", 30.0), cfg.get("speed_cap", 18.0)
    venv = DummyVecEnv([lambda: RateVelAviary(task=task, episode_len_sec=ep_len, max_speed=20.0,
                                              pos_range=pr, speed_cap=sc)])
    venv = VecNormalize.load(os.path.join(out_dir, "vecnormalize.pkl"), venv)
    venv.training = False; venv.norm_reward = False
    mp = os.path.join(out_dir, "best", "best_model.zip")
    return algo.load(mp), venv, task, unwrap_base(venv)


def run(out_dir, goal_fn, n_steps, wind=(0, 0, 0), mass=10.0):
    """Drive policy to track goal_fn(t) as a position reference. Truncates at first done."""
    model, venv, task, base = load(out_dir)
    base.MASS_RANGE = (mass, mass)
    venv.seed(0); venv.reset(); base.wind = np.array(wind, float)
    dt = base.CTRL_TIMESTEP
    p_hist, g_hist, t = [], [], 0.0
    for _ in range(n_steps):
        p = base.pos[0].copy(); goal = np.asarray(goal_fn(t), float)
        if task == "velocity":
            vff = (np.asarray(goal_fn(t + dt), float) - goal) / dt
            v_cmd = vff + KP * (goal - p)
            s = np.linalg.norm(v_cmd)
            if s > VMAX: v_cmd = v_cmd * (VMAX / s)
            base.target_vel = v_cmd
        else:
            base.target_pos = goal
        obs = venv.normalize_obs(base._computeObs()[None])
        a, _ = model.predict(obs, deterministic=True)
        _, _, done, _ = venv.step(a)
        p_hist.append(p); g_hist.append(goal); t += dt
        if done[0]:                       # crash/timeout -> stop before auto-reset teleports
            break
    venv.close()
    return np.array(p_hist), np.array(g_hist), dt


def colors(n): return plt.cm.viridis(np.linspace(0, 0.9, n))


# ---------- hover-hold: calm + 15 m/s wind ----------
def fig_hover(models, fname, title):
    N = int(10 / 0.02)
    fig, axs = plt.subplots(1, 2, figsize=(13, 4.6), sharey=True)
    cs = colors(len(models))
    for ax, (wind, wl) in zip(axs, [((0, 0, 0), "calm"), ((15, 0, 0), "15 m/s wind")]):
        for (lab, d), c in zip(models, cs):
            p, g, dt = run(d, lambda t: START, N, wind=wind)
            err = np.linalg.norm(p - g, axis=1)
            ax.plot(np.arange(len(err)) * dt, err, color=c, label=f"{lab}  (final {err[-int(2/dt):].mean():.2f} m)")
        ax.set_xlabel("time (s)"); ax.set_title(f"Hover hold — {wl}"); ax.grid(alpha=.3); ax.legend(fontsize=7)
    axs[0].set_ylabel("position error (m)")
    fig.suptitle(title); fig.tight_layout()
    fig.savefig(f"{OUT}/{fname}", dpi=120); plt.close(fig); print(fname)


# ---------- circular path (r=3 m, 8 s period), calm ----------
def fig_path(models, fname, title):
    N = int(16 / 0.02); c0 = np.array([0, 0, 2.0]); r = 3.0; w = 2 * np.pi / 8
    circle = lambda t: c0 + np.array([r * np.cos(w * t) - r, r * np.sin(w * t), 0])
    fig, ax = plt.subplots(figsize=(6.6, 6.2)); cs = colors(len(models))
    ref = None
    for (lab, d), c in zip(models, cs):
        p, g, dt = run(d, circle, N)
        if ref is None:
            ax.plot(g[:, 0], g[:, 1], "k--", lw=2, label="reference"); ref = g
        k0 = int(2 / dt); rms = np.sqrt((np.linalg.norm(p[k0:] - g[k0:], axis=1) ** 2).mean()) if len(p) > k0 else np.nan
        ax.plot(p[:, 0], p[:, 1], color=c, label=f"{lab}  (RMS {rms:.2f} m)", alpha=0.9)
    ax.set_xlabel("x (m)"); ax.set_ylabel("y (m)"); ax.axis("equal"); ax.grid(alpha=.3); ax.legend(fontsize=7)
    ax.set_title(title); fig.tight_layout()
    fig.savefig(f"{OUT}/{fname}", dpi=120); plt.close(fig); print(fname)


if __name__ == "__main__":
    fig_hover(VEL, "fig_all_hover_velocity.png", "Hover via velocity policy + outer P-loop")
    fig_path(VEL, "fig_all_path_velocity.png", "Circular path (calm) — velocity policies + outer loop")
    fig_hover(POS, "fig_all_hover_position.png", "Hover via position policy (direct goal)")
    fig_path(POS, "fig_all_path_position.png", "Circular path (calm) — position policies")
    print("done ->", OUT)
