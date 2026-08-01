"""Train a PPO policy on the QuadNav pure-Python env (Duck18 quadrotor).

QuadNav already has a Betaflight acro-rate PID inner loop, so the RL action is a
CTBR outer-loop command — action = [roll_rate, pitch_rate, yaw_rate, throttle],
exactly like RateVelAviary. Key differences from the pybullet setup drive the
config below:

  * Obs is ALREADY normalized (tanh/clip to ~[-1,1]) -> we do NOT VecNormalize the
    obs (norm_reward only, to scale the value target).
  * Domain randomization (mass, inertia, motor lag, init attitude/velocity, IMU
    gain/bias, GPS, wind) is baked into the env -> we add none.
  * Pure-Python plant at ~400 steps/s/worker -> SubprocVecEnv is mandatory for
    throughput (DummyVecEnv gets no speedup under the GIL).
  * Episodes are 30 s (3000 steps) with a dense reward -> gamma bumped to 0.995.

Examples
--------
    python train_quadnav.py --smoke
    python train_quadnav.py --timesteps 5000000 --n-envs 8
"""
import argparse
import os
import json

import gymnasium as gym
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv, VecNormalize
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback

import quadnav_python                        # registers QuadNav-v0
from quadnav_python import QuadNavEnv


def build_env(n_envs, seed, subproc, env_kwargs, norm_reward, training, gamma):
    cls = SubprocVecEnv if (subproc and n_envs > 1) else DummyVecEnv
    venv = make_vec_env(QuadNavEnv, n_envs=n_envs, seed=seed,
                        env_kwargs=env_kwargs, vec_env_cls=cls)
    # NB: norm_obs=False — QuadNav obs is already normalized to ~[-1,1]. Re-normalizing
    # is redundant and amplifies noise on tanh-saturated dims. Only scale the reward.
    env = VecNormalize(venv, norm_obs=False, norm_reward=norm_reward,
                       gamma=gamma, training=training)
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timesteps", type=int, default=5_000_000)
    ap.add_argument("--n-envs", type=int, default=8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", type=str, default="results_quadnav")
    ap.add_argument("--tf", type=float, default=30.0, help="episode length (s)")
    ap.add_argument("--gamma", type=float, default=0.995)
    ap.add_argument("--net", type=str, default="128,128")
    ap.add_argument("--lift", action="store_true", help="short-range low-speed lift task")
    ap.add_argument("--no-noise", action="store_true", help="disable IMU/GPS sensor noise")
    ap.add_argument("--no-wind", action="store_true")
    ap.add_argument("--no-subproc", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    if args.smoke:
        args.timesteps, args.n_envs = 30_000, 2
    os.makedirs(args.out_dir, exist_ok=True)
    net = [int(x) for x in args.net.split(",")]
    json.dump(dict(tf=args.tf, gamma=args.gamma, net=net, lift=args.lift,
                   noise=not args.no_noise, wind=not args.no_wind),
              open(os.path.join(args.out_dir, "config.json"), "w"))

    env_kwargs = dict(tf=args.tf, is_lift=args.lift,
                      noise=not args.no_noise, wind=not args.no_wind)
    train_env = build_env(args.n_envs, args.seed, not args.no_subproc,
                          env_kwargs, norm_reward=True, training=True, gamma=args.gamma)
    # eval on the SAME (noisy) distribution used in deployment; norm_obs is off so the
    # eval env needs no shared statistics. Separate seed to decorrelate from training.
    eval_env = build_env(1, args.seed + 999, not args.no_subproc,
                         env_kwargs, norm_reward=False, training=False, gamma=args.gamma)

    model = PPO(
        "MlpPolicy", train_env,
        n_steps=2048, batch_size=4096, n_epochs=10,
        gamma=args.gamma, gae_lambda=0.95, clip_range=0.2,
        ent_coef=0.0, learning_rate=3e-4, max_grad_norm=0.5,
        policy_kwargs=dict(net_arch=net),
        tensorboard_log=os.path.join(args.out_dir, "tb"),
        seed=args.seed, verbose=1,
    )

    ckpt = CheckpointCallback(save_freq=max(200_000 // args.n_envs, 1),
                              save_path=os.path.join(args.out_dir, "ckpts"),
                              name_prefix="ppo_quadnav")
    evalcb = EvalCallback(
        eval_env, best_model_save_path=os.path.join(args.out_dir, "best"),
        log_path=os.path.join(args.out_dir, "eval"),
        eval_freq=max(100_000 // args.n_envs, 1),
        n_eval_episodes=10, deterministic=True, render=False)

    model.learn(total_timesteps=args.timesteps, callback=[ckpt, evalcb], progress_bar=True)

    model.save(os.path.join(args.out_dir, "ppo_quadnav_final"))
    train_env.save(os.path.join(args.out_dir, "vecnormalize.pkl"))
    print(f"[DONE] saved PPO model to {args.out_dir}/  (net={net}, gamma={args.gamma})")
    train_env.close(); eval_env.close()


if __name__ == "__main__":
    main()
