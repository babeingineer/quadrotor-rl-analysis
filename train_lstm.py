"""RecurrentPPO (LSTM) trainer for the velyaw task — same env/reward stack as train.py.

Purpose: implicit per-episode system identification. The +/-20% aero-coefficient DR (plus Xg,
mass, motor lag, fin gains) makes every episode a slightly different aircraft; a memoryless
MLP flies the average one. The LSTM can infer THIS episode's parameters from the response to
its own actions and adapt (the memory-study lesson: keep the hand features anyway — they
helped even the LSTM).  config.json marks algo="recurrent_ppo" so eval threads hidden state.

    python train_lstm.py --xwing-aero --yaw-bias 0.3 --max-speed 25 --wind-max 15 \
        --yaw-gate --yaw-att-gate --vel-precision 0.7 --cov-width 5 --ent-coef 0.003 \
        --gamma 0.997 --episode-len 14 --n-envs 10 --timesteps 10000000 --out-dir results_velyaw_lstm
"""
import argparse
import os
import json

from sb3_contrib import RecurrentPPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv, VecNormalize
from stable_baselines3.common.callbacks import CheckpointCallback, BaseCallback


class VecNormSaveCallback(BaseCallback):
    """Save VecNormalize stats on the checkpoint cadence so a killed run can resume
    consistently (model ckpt + matching obs-normalization stats)."""
    def __init__(self, env, path, every):
        super().__init__(); self.env = env; self.path = path; self.every = every; self._last = 0
    def _on_step(self):
        if self.num_timesteps - self._last >= self.every:
            self.env.save(self.path); self._last = self.num_timesteps
        return True

from rate_vel_aviary import RateVelAviary
from progress_callback import ProgressPlotCallback


def norm_env(n_envs, seed, subproc, norm_reward, training, env_kwargs, norm_gamma=0.99):
    cls = SubprocVecEnv if (subproc and n_envs > 1) else DummyVecEnv
    venv = make_vec_env(RateVelAviary, n_envs=n_envs, seed=seed,
                        env_kwargs=env_kwargs, vec_env_cls=cls)
    env = VecNormalize(venv, norm_obs=True, norm_reward=norm_reward,
                       clip_obs=10.0, gamma=norm_gamma, training=training)
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timesteps", type=int, default=10_000_000)
    ap.add_argument("--n-envs", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", type=str, default="results_velyaw_lstm")
    ap.add_argument("--max-speed", type=float, default=25.0)
    ap.add_argument("--speed-min", type=float, default=0.0)
    ap.add_argument("--wind-max", type=float, default=15.0)
    ap.add_argument("--yaw-bias", type=float, default=0.0)
    ap.add_argument("--yaw-weight", type=float, default=1.0)
    ap.add_argument("--yaw-width", type=float, default=0.35)
    ap.add_argument("--yaw-gate", action="store_true")
    ap.add_argument("--yaw-gate-floor", type=float, default=0.2)
    ap.add_argument("--yaw-att-gate", action="store_true")
    ap.add_argument("--vel-precision", type=float, default=0.0)
    ap.add_argument("--cov-width", type=float, default=0.0)
    ap.add_argument("--ent-coef", type=float, default=0.0)
    ap.add_argument("--gamma", type=float, default=0.99)
    ap.add_argument("--episode-len", type=float, default=8.0)
    ap.add_argument("--xwing-aero", action="store_true")
    ap.add_argument("--tough-init", type=float, default=0.0)
    ap.add_argument("--lstm-size", type=int, default=256)
    ap.add_argument("--n-steps", type=int, default=1024,
                    help="rollout length; shorter = smaller BPTT buffers (RAM) + faster updates")
    ap.add_argument("--net", type=str, default="256,256")
    ap.add_argument("--no-subproc", action="store_true")
    ap.add_argument("--device", type=str, default="cpu")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    if args.smoke:
        args.timesteps, args.n_envs = 8_000, 2
    os.makedirs(args.out_dir, exist_ok=True)
    json.dump({"algo": "recurrent_ppo", "lstm_size": args.lstm_size,
               "max_speed": args.max_speed, "speed_min": args.speed_min,
               "wind_max": args.wind_max, "use_integral": True, "use_yaw_integral": True,
               "use_wind_est": True, "yaw_width": args.yaw_width, "yaw_weight": args.yaw_weight,
               "yaw_bias": args.yaw_bias, "heading_frame": False,
               "xwing_aero": args.xwing_aero, "tough_init": args.tough_init,
               "wind_curriculum": False, "yaw_gate": args.yaw_gate,
               "yaw_gate_floor": args.yaw_gate_floor, "vel_precision": args.vel_precision,
               "yaw_att_gate": args.yaw_att_gate, "cov_width": args.cov_width,
               "ent_coef": args.ent_coef, "gamma": args.gamma,
               "episode_len": args.episode_len},
              open(os.path.join(args.out_dir, "config.json"), "w"))

    base_kwargs = dict(episode_len_sec=args.episode_len, max_speed=args.max_speed,
                       speed_min=args.speed_min, wind_max=args.wind_max,
                       yaw_reward_width=args.yaw_width, yaw_weight=args.yaw_weight,
                       yaw_bias_max=args.yaw_bias, use_xwing_aero=args.xwing_aero,
                       yaw_gate=args.yaw_gate, yaw_gate_floor=args.yaw_gate_floor,
                       vel_precision=args.vel_precision, yaw_att_gate=args.yaw_att_gate,
                       cov_width=args.cov_width)
    train_kwargs = dict(base_kwargs, randomize_init=True, tough_init_frac=args.tough_init)
    eval_kwargs = dict(base_kwargs, randomize_init=False)
    train_env = norm_env(args.n_envs, args.seed, not args.no_subproc, True, True,
                         train_kwargs, norm_gamma=args.gamma)
    eval_env = norm_env(1, args.seed + 999, not args.no_subproc, False, False,
                        eval_kwargs, norm_gamma=args.gamma)

    model = RecurrentPPO(
        "MlpLstmPolicy", train_env,
        n_steps=args.n_steps, batch_size=4096, n_epochs=10,
        gamma=args.gamma, gae_lambda=0.95, clip_range=0.2,
        ent_coef=args.ent_coef, learning_rate=3e-4, max_grad_norm=0.5,
        policy_kwargs=dict(net_arch=[int(x) for x in args.net.split(",")],
                           lstm_hidden_size=args.lstm_size),
        tensorboard_log=os.path.join(args.out_dir, "tb"),
        seed=args.seed, verbose=1, device=args.device,
    )

    ckpt = CheckpointCallback(save_freq=max(200_000 // args.n_envs, 1),
                              save_path=os.path.join(args.out_dir, "ckpts"),
                              name_prefix="ppo_ratevel")
    evalcb = ProgressPlotCallback(
        eval_env, out_dir=args.out_dir, tag="RecurrentPPO-velyaw",
        best_model_save_path=os.path.join(args.out_dir, "best"),
        log_path=os.path.join(args.out_dir, "eval"),
        eval_freq=max(100_000 // args.n_envs, 1),
        n_eval_episodes=10, deterministic=True, render=False)

    vns = VecNormSaveCallback(train_env, os.path.join(args.out_dir, "vecnormalize.pkl"),
                              every=200_000)
    model.learn(total_timesteps=args.timesteps, callback=[ckpt, evalcb, vns], progress_bar=True)

    model.save(os.path.join(args.out_dir, "ppo_ratevel_final"))
    train_env.save(os.path.join(args.out_dir, "vecnormalize.pkl"))
    print(f"[DONE] saved RecurrentPPO model + vecnormalize to {args.out_dir}/")
    train_env.close(); eval_env.close()


if __name__ == "__main__":
    main()
