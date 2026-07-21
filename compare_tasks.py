"""Compare two ways to get POSITION control on the heavy quad:

  A) velocity-PPO  (results_obs)  + an outer position P-loop:
         v_target = v_ff + Kp*(goal - pos), clipped to v_max
  B) position-PPO  (results_pos)  driven directly with the goal position (carrot).

Both are evaluated on the SAME tasks: hover-hold, step response (agility), and a
circular path. Reports position error + timing, and saves plots.

Usage:  python compare_tasks.py
"""
import argparse, json, os
import numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from rate_vel_aviary import RateVelAviary
from progress_callback import unwrap_base

VMAX = 18.0     # outer-loop velocity clamp (matches position policy's speed cap)
KP = 1.5        # outer position-loop gain


def load(out_dir, ep_len=60.0):
    cfg = json.load(open(os.path.join(out_dir, "config.json")))
    task = cfg.get("task", "velocity"); assert cfg.get("n_stack", 1) == 1
    pr, sc = cfg.get("pos_range", 30.0), cfg.get("speed_cap", 18.0)
    venv = DummyVecEnv([lambda: RateVelAviary(task=task, episode_len_sec=ep_len, max_speed=20.0,
                                              pos_range=pr, speed_cap=sc)])
    venv = VecNormalize.load(os.path.join(out_dir, "vecnormalize.pkl"), venv)
    venv.training = False; venv.norm_reward = False
    mp = os.path.join(out_dir, "best", "best_model.zip")
    if not os.path.exists(mp): mp = os.path.join(out_dir, "ppo_ratevel_final.zip")
    return PPO.load(mp), venv, task, unwrap_base(venv)


def run(out_dir, goal_fn, n_steps, wind=(0,0,0), mass=10.0):
    """Drive the policy to track goal_fn(t) as a POSITION reference. Returns pos/goal traces."""
    model, venv, task, base = load(out_dir)
    base.MASS_RANGE = (mass, mass)
    venv.seed(0); venv.reset(); base.wind = np.array(wind, float)
    dt = base.CTRL_TIMESTEP
    p_hist, g_hist, t = [], [], 0.0
    for k in range(n_steps):
        p = base.pos[0].copy(); goal = np.asarray(goal_fn(t), float)
        if task == "velocity":                       # outer position P-loop + feedforward
            vff = (np.asarray(goal_fn(t + dt), float) - goal) / dt
            v_cmd = vff + KP * (goal - p)
            s = np.linalg.norm(v_cmd)
            if s > VMAX: v_cmd = v_cmd * (VMAX / s)
            base.target_vel = v_cmd
        else:                                         # position policy: hand it the goal
            base.target_pos = goal
        obs = venv.normalize_obs(base._computeObs()[None])   # obs consistent with just-set target
        a, _ = model.predict(obs, deterministic=True)
        venv.step(a)
        p_hist.append(p); g_hist.append(goal); t += dt
    venv.close()
    return np.array(p_hist), np.array(g_hist), dt


def metrics(p, g, dt):
    err = np.linalg.norm(p - g, axis=1)
    return dict(mean=err.mean(), max=err.max(), final=err[-int(2/dt):].mean())


def main():
    P, S = "results_obs", "results_pos"        # velocity-PPO+loop, position-PPO
    rows = []

    # ---- Test 1: HOVER hold (goal = start point) ----
    start = np.array([0, 0, 2.0]); N = int(8/0.02)
    for wind, wl in [((0,0,0), "calm"), ((15,0,0), "wind15")]:
        gv = run(P, lambda t: start, N, wind=wind); gs = run(S, lambda t: start, N, wind=wind)
        mv, ms = metrics(*gv), metrics(*gs)
        rows.append((f"hover-hold ({wl})", "max pos err (m)", mv['max'], ms['max']))
        rows.append((f"hover-hold ({wl})", "mean pos err (m)", mv['mean'], ms['mean']))
        if wl == "wind15": hov = (gv, gs)

    # ---- Test 2: STEP response 4 m (+x), agility ----
    N = int(6/0.02)
    step_goal = lambda t: np.array([4.0, 0, 2.0])
    gv, gs = run(P, step_goal, N), run(S, step_goal, N)
    def settle_time(p, g, dt, tol=0.3):
        err = np.linalg.norm(p - g, axis=1)
        below = np.where(err < tol)[0]
        return below[0]*dt if len(below) else np.nan
    for lab, (p,g,dt) in [("velocity+loop", gv), ("position", gs)]:
        pass
    stv, sts = settle_time(*gv), settle_time(*gs)
    ovv = (gv[0][:,0].max()-4.0); ovs = (gs[0][:,0].max()-4.0)   # overshoot past 4 m in x
    rows.append(("step 4m", "time to <0.3m (s)", stv, sts))
    rows.append(("step 4m", "overshoot (m)", max(0,ovv), max(0,ovs)))
    rows.append(("step 4m", "final err (m)", metrics(*gv)['final'], metrics(*gs)['final']))
    step_traces = (gv, gs)

    # ---- Test 3: circular PATH (r=3 m, period 8 s) ----
    N = int(16/0.02); c = np.array([0,0,2.0]); r=3.0; w=2*np.pi/8
    circle = lambda t: c + np.array([r*np.cos(w*t)-r, r*np.sin(w*t), 0])   # start at (0,0,2)
    for wind, wl in [((0,0,0),"calm"), ((10,0,0),"wind10")]:
        gv = run(P, circle, N, wind=wind); gs = run(S, circle, N, wind=wind)
        # ignore first 2 s (entry transient) for path RMS
        k0 = int(2/gv[2])
        rv = np.linalg.norm(gv[0][k0:]-gv[1][k0:],axis=1); rs = np.linalg.norm(gs[0][k0:]-gs[1][k0:],axis=1)
        rows.append((f"circle ({wl})", "RMS path err (m)", np.sqrt((rv**2).mean()), np.sqrt((rs**2).mean())))
        if wl=="calm": circ = (gv, gs)

    # ---- table ----
    print(f"\n{'task':<20}{'metric':<20}{'VEL+loop':>10}{'POSITION':>10}{'better':>9}")
    print("-"*69)
    for task, metric, v, s in rows:
        better = "pos" if s < v else "vel"
        print(f"{task:<20}{metric:<20}{v:>10.3f}{s:>10.3f}{better:>9}")

    # ---- plots ----
    fig, ax = plt.subplots(1,3, figsize=(15,4.3))
    (gv,gs)=hov; t=np.arange(len(gv[0]))*gv[2]
    ax[0].plot(t, np.linalg.norm(gv[0]-gv[1],axis=1), label="vel+loop")
    ax[0].plot(t, np.linalg.norm(gs[0]-gs[1],axis=1), label="position")
    ax[0].set_title("Hover hold, 15 m/s wind"); ax[0].set_xlabel("t (s)"); ax[0].set_ylabel("pos err (m)"); ax[0].legend(); ax[0].grid(alpha=.3)
    (gv,gs)=step_traces; t=np.arange(len(gv[0]))*gv[2]
    ax[1].plot(t, gv[0][:,0], label="vel+loop"); ax[1].plot(t, gs[0][:,0], label="position")
    ax[1].axhline(4.0, ls="--", c="k", label="target"); ax[1].set_title("Step response (x, 4 m)")
    ax[1].set_xlabel("t (s)"); ax[1].set_ylabel("x (m)"); ax[1].legend(); ax[1].grid(alpha=.3)
    (gv,gs)=circ
    ax[2].plot(gv[1][:,0], gv[1][:,1], "k--", label="reference")
    ax[2].plot(gv[0][:,0], gv[0][:,1], label="vel+loop"); ax[2].plot(gs[0][:,0], gs[0][:,1], label="position")
    ax[2].set_title("Circular path (calm)"); ax[2].set_xlabel("x (m)"); ax[2].set_ylabel("y (m)")
    ax[2].axis("equal"); ax[2].legend(); ax[2].grid(alpha=.3)
    fig.tight_layout(); fig.savefig("compare_tasks.png", dpi=120)
    print("\n[saved] compare_tasks.png")


if __name__ == "__main__":
    main()
