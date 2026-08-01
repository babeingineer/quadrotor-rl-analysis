"""Evaluate memory policies (MLP / frame-stack / LSTM) on the tailsitter velocity task, all
through the REAL vec-env stack so wrapper order (VecNormalize outside VecFrameStack) is identical
to training. Constant target per episode (one-step lag irrelevant); LSTM state + episode_start
threaded through predict. Same band metric / seeds as eval_ts for comparability.
"""
import json, numpy as np
from stable_baselines3 import PPO
from sb3_contrib import RecurrentPPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize, VecFrameStack
from rate_vel_aviary import RateVelAviary
from progress_callback import unwrap_base
from eval_ts import report


def load(D, ep=20.0):
    cfg = json.load(open(f"{D}/config.json"))
    n_stack = cfg.get("n_stack", 1); ui = cfg.get("use_integral", False)
    uw = cfg.get("use_wind_est", True)
    is_lstm = cfg.get("algo") == "recurrent_ppo"
    venv = DummyVecEnv([lambda: RateVelAviary(task="velocity", episode_len_sec=ep,
                                              max_speed=80.0, use_vel_integral=ui, use_wind_est=uw)])
    if n_stack > 1:
        venv = VecFrameStack(venv, n_stack=n_stack)      # inside VecNormalize, matches build_stacked
    venv = VecNormalize.load(f"{D}/vecnormalize.pkl", venv)
    venv.training = False; venv.norm_reward = False
    algo = RecurrentPPO if is_lstm else PPO
    return algo.load(f"{D}/best/best_model.zip"), venv, unwrap_base(venv), is_lstm


def evaluate(D, n=240, seed=100, ep=15.0):
    model, venv, base, is_lstm = load(D, ep=ep + 5.0)    # episode_len margin -> no mid-eval reset
    dt = base.CTRL_TIMESTEP; N = int(ep / dt); k0 = N - int(3 / dt)
    rng = np.random.default_rng(seed)
    rows = []
    for i in range(n):
        d = rng.normal(size=3); d /= np.linalg.norm(d)
        tgt_speed = float(rng.uniform(0, 80)); tgt = d * tgt_speed
        wind_on = bool(i % 2)
        base.MASS_RANGE = (float(rng.uniform(2, 5)),) * 2    # set before reset -> housekeeping samples
        obs = venv.reset()
        if wind_on:
            wd = rng.normal(size=3); wd /= np.linalg.norm(wd); base.wind = wd * rng.uniform(0, 20)
        else:
            base.wind = np.zeros(3)
        state = None; ep_start = np.ones(1, dtype=bool); errs = []
        for k in range(N):
            base.target_vel = tgt
            action, state = model.predict(obs, state=state, episode_start=ep_start, deterministic=True)
            obs, _, done, _ = venv.step(action)
            ep_start = np.zeros(1, dtype=bool)
            if k >= k0:
                errs.append(np.linalg.norm(base.vel[0] - tgt))
        band = ("hover(0-1)" if tgt_speed < 1 else "low(1-20)" if tgt_speed < 20
                else "mid(20-50)" if tgt_speed < 50 else "high(50-80)")
        rows.append((band, wind_on, np.mean(errs), False, tgt_speed))
    venv.close()
    return rows


if __name__ == "__main__":
    import sys
    for D in sys.argv[1:] or ["results_m_mlp", "results_m_fs", "results_m_lstm"]:
        print(f"\n########## {D} ##########")
        try:
            report(evaluate(D))
        except Exception as e:
            print(f"  (skipped: {type(e).__name__}: {e})")
