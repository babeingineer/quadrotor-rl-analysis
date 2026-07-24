"""Evaluate the tailsitter velocity-tracking PPO policy: steady-state speed error
broken down by target-speed band and wind, plus crash rate. Also saves a tracking
time-series figure (incl. the hover->cruise pitch-over)."""
import os, json
import numpy as np
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import pybullet as p
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from rate_vel_aviary import RateVelAviary
from progress_callback import unwrap_base

def load(D, ep=15.0):
    json.load(open(f"{D}/config.json"))
    venv = DummyVecEnv([lambda: RateVelAviary(task="velocity", episode_len_sec=ep, max_speed=80.0)])
    venv = VecNormalize.load(f"{D}/vecnormalize.pkl", venv)
    venv.training = False; venv.norm_reward = False
    return PPO.load(f"{D}/best/best_model.zip"), venv, unwrap_base(venv)


def evaluate(D, n=240, seed=100, ep=15.0):
    """Same random targets/winds/masses for every D (seed fixed) -> fair comparison.
    Measures steady-state error over the final 3 s of an `ep`-second rollout."""
    model, venv, base = load(D, ep=ep)
    dt = base.CTRL_TIMESTEP; N = int(ep / dt); k0 = N - int(3 / dt)
    rng = np.random.default_rng(seed)
    rows = []   # (speed_band, wind_on, err, crashed, tgt_speed)
    for i in range(n):
        venv.seed(1000 + i); venv.reset()          # seed by index -> identical across D
        d = rng.normal(size=3); d /= np.linalg.norm(d)
        tgt_speed = float(rng.uniform(0, 80)); tgt = d * tgt_speed
        wind_on = bool(i % 2)
        if wind_on:
            wd = rng.normal(size=3); wd /= np.linalg.norm(wd)
            base.wind = wd * rng.uniform(0, 20)
        else:
            base.wind = np.zeros(3)
        base.MASS_RANGE = (float(rng.uniform(2, 5)),) * 2
        errs, crashed = [], False
        for k in range(N):
            base.target_vel = tgt
            obs = venv.normalize_obs(base._computeObs()[None])
            a, _ = model.predict(obs, deterministic=True)
            _, _, done, _ = venv.step(a)
            if k >= k0:
                errs.append(np.linalg.norm(base.vel[0] - tgt))
            if done[0]: crashed = True; break
        band = ("hover(0-1)" if tgt_speed < 1 else "low(1-20)" if tgt_speed < 20
                else "mid(20-50)" if tgt_speed < 50 else "high(50-80)")
        rows.append((band, wind_on, np.mean(errs) if errs else np.nan, crashed, tgt_speed))
    venv.close()
    return rows


def report(rows):
    bands = ["hover(0-1)", "low(1-20)", "mid(20-50)", "high(50-80)"]
    print(f"\n{'band':<12}{'n':>4}{'mean err':>10}{'err(calm)':>11}{'err(wind)':>11}")
    print("-" * 48)
    allc = [r for r in rows if not r[3]]
    for b in bands:
        rs = [r for r in allc if r[0] == b]
        if not rs: continue
        e = np.mean([r[2] for r in rs])
        ec = [r[2] for r in rs if not r[1]]; ew = [r[2] for r in rs if r[1]]
        print(f"{b:<12}{len(rs):>4}{e:>10.2f}{(np.mean(ec) if ec else np.nan):>11.2f}"
              f"{(np.mean(ew) if ew else np.nan):>11.2f}")
    print("-" * 48)
    err_all = np.mean([r[2] for r in allc])
    crash = sum(r[3] for r in rows) / len(rows) * 100
    print(f"{'ALL':<12}{len(allc):>4}{err_all:>10.2f}  m/s      crash {crash:.1f}%")


def fig_track(D="results_ts2"):
    model, venv, base = load(D, ep=10.0)
    venv.seed(7); venv.reset(); base.wind = np.array([10.0, 0, 0]); base.MASS_RANGE = (3.5, 3.5)
    tgt = np.array([55.0, 0.0, 0.0])                 # fast forward -> must transition
    dt = base.CTRL_TIMESTEP
    vs, pitch, ts, t = [], [], [], 0.0
    for _ in range(500):
        base.target_vel = tgt
        obs = venv.normalize_obs(base._computeObs()[None]); a, _ = model.predict(obs, deterministic=True); venv.step(a)
        vs.append(base.vel[0].copy())
        R = np.array(p.getMatrixFromQuaternion(base.quat[0])).reshape(3, 3)
        pitch.append(np.degrees(np.arccos(np.clip(R[2, 2], -1, 1))))  # tilt of body-z from vertical
        ts.append(t); t += dt
    venv.close(); vs = np.array(vs); ts = np.array(ts)
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.4))
    for i, l in enumerate(["vx", "vy", "vz"]):
        ax[0].plot(ts, vs[:, i], color=f"C{i}", label=l); ax[0].axhline(tgt[i], ls="--", color=f"C{i}", alpha=.5)
    ax[0].set_xlabel("time (s)"); ax[0].set_ylabel("velocity (m/s)"); ax[0].grid(alpha=.3); ax[0].legend()
    ax[0].set_title("Velocity tracking: target (55,0,0) m/s, 10 m/s wind")
    ax[1].plot(ts, pitch, "C3"); ax[1].set_xlabel("time (s)"); ax[1].set_ylabel("thrust-axis tilt from vertical (deg)")
    ax[1].grid(alpha=.3); ax[1].set_title("Hover->cruise transition (0=hover, 90=full forward)")
    fig.tight_layout(); os.makedirs("docs", exist_ok=True)
    fig.savefig("docs/fig_ts_track.png", dpi=120); plt.close(fig); print("saved docs/fig_ts_track.png")


if __name__ == "__main__":
    for D in ["results_ts", "results_ts2", "results_ts3"]:
        print(f"\n########## {D} ##########")
        report(evaluate(D))
    fig_track("results_ts3")
