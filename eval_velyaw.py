"""Evaluate a velyaw policy: steady-state velocity error (by target-speed band) AND
heading error (deg), plus crash rate. Uses the saved VecNormalize stats and best model.

    python eval_velyaw.py --dir results_velyaw_xwaero --episodes 120
"""
import argparse, json, os
import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from rate_vel_aviary import RateVelAviary


class _Predictor:
    """Uniform predict() for MLP and LSTM policies. For RecurrentPPO, threads the hidden
    state and episode_start flag; call reset() after every venv.reset()."""
    def __init__(self, model, recurrent):
        self.m = model; self.rec = recurrent; self.state = None; self.start = True

    def reset(self):
        self.state = None; self.start = True

    def predict(self, obs, deterministic=True):
        if self.rec:
            a, self.state = self.m.predict(obs, state=self.state,
                                           episode_start=np.array([self.start]),
                                           deterministic=deterministic)
            self.start = False
            return a, None
        return self.m.predict(obs, deterministic=deterministic)


def load(D, ep_len=10.0, **overrides):
    cfg = json.load(open(f"{D}/config.json"))
    kw = dict(episode_len_sec=ep_len, max_speed=cfg.get("max_speed", 25.0),
              speed_min=cfg.get("speed_min", 0.0),
              wind_max=cfg.get("wind_max", 20.0),
              use_wind_est=cfg.get("use_wind_est", True),
              use_vel_integral=cfg.get("use_integral", True),
              use_yaw_integral=cfg.get("use_yaw_integral", True),
              yaw_reward_width=cfg.get("yaw_width", 0.35),
              yaw_weight=cfg.get("yaw_weight", 1.0),
              yaw_bias_max=cfg.get("yaw_bias", 0.0),
              velyaw_heading_frame=cfg.get("heading_frame", False),
              use_xwing_aero=cfg.get("xwing_aero", False),
              yaw_gate=cfg.get("yaw_gate", False),
              yaw_gate_floor=cfg.get("yaw_gate_floor", 0.2),
              vel_precision=cfg.get("vel_precision", 0.0),
              yaw_att_gate=cfg.get("yaw_att_gate", False),
              cov_width=cfg.get("cov_width", 0.0),
              aero_dr=cfg.get("aero_dr", True),
              integral_tau=cfg.get("integral_tau", 3.0),
              kp_rate=tuple(float(x) for x in cfg.get("kp_rate", "6,6,4").split(",")),
              ki_rate=tuple(float(x) for x in cfg.get("ki_rate", "0.5,0.5,0.3").split(",")),
              randomize_init=False)
    kw.update(overrides)
    venv = DummyVecEnv([lambda: RateVelAviary(**kw)])
    venv = VecNormalize.load(f"{D}/vecnormalize.pkl", venv)
    venv.training = False; venv.norm_reward = False
    recurrent = cfg.get("algo") == "recurrent_ppo"
    mp = f"{D}/best/best_model.zip"
    if not os.path.exists(mp):
        mp = f"{D}/ppo_ratevel_final.zip"      # fallback (e.g. smoke runs with no eval yet)
    if recurrent:
        from sb3_contrib import RecurrentPPO
        model = RecurrentPPO.load(mp, device="cpu")
    else:
        model = PPO.load(mp, device="cpu")
    base = venv.venv.envs[0].unwrapped
    return _Predictor(model, recurrent), venv, base


def evaluate(D, n=120, ep_len=10.0, steady_window=3.0, **overrides):
    """Steady-state = mean over the final `steady_window` seconds of each episode."""
    model, venv, base = load(D, ep_len, **overrides)
    dt = base.CTRL_TIMESTEP; N = int(ep_len / dt); k0 = N - int(steady_window / dt)
    rows = []
    for i in range(n):
        venv.seed(1000 + i)
        obs = venv.reset()
        model.reset()
        tgt_speed = float(np.linalg.norm(base.target_vel))
        verrs, yerrs, crashed = [], [], False
        for k in range(N):
            a, _ = model.predict(obs, deterministic=True)
            obs, _, done, infos = venv.step(a)
            if k >= k0:
                verrs.append(infos[0]["vel_error"])
                yerrs.append(abs(np.degrees(infos[0]["yaw_error"])))
            if done[0]:
                crashed = k < N - 1
                break
        band = ("hover(0-1)" if tgt_speed < 1 else "low(1-10)" if tgt_speed < 10 else
                "mid(10-18)" if tgt_speed < 18 else "high(18-25)")
        rows.append((band, np.mean(verrs) if verrs else np.nan,
                     np.mean(yerrs) if yerrs else np.nan, crashed, tgt_speed))
    venv.close()
    return rows


def report(rows):
    bands = ["hover(0-1)", "low(1-10)", "mid(10-18)", "high(18-25)"]
    ok = [r for r in rows if not r[3]]
    print(f"\n{'band':<12}{'n':>4}{'vel err (m/s)':>15}{'yaw err (deg)':>15}")
    print("-" * 46)
    for b in bands:
        rs = [r for r in ok if r[0] == b]
        if not rs:
            continue
        print(f"{b:<12}{len(rs):>4}{np.mean([r[1] for r in rs]):>15.2f}"
              f"{np.mean([r[2] for r in rs]):>15.1f}")
    print("-" * 46)
    crash = sum(r[3] for r in rows) / len(rows) * 100
    print(f"{'ALL':<12}{len(ok):>4}{np.mean([r[1] for r in ok]):>15.2f}"
          f"{np.mean([r[2] for r in ok]):>15.1f}   crash {crash:.1f}%")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="results_velyaw_xwaero")
    ap.add_argument("--episodes", type=int, default=120)
    args = ap.parse_args()
    print(f"########## {args.dir} ##########")
    report(evaluate(args.dir, n=args.episodes))
