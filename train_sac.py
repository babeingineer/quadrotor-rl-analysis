"""Train a SAC policy on RateVelAviary — same env/obs/reward/frame-stacking as
train.py (PPO), for a head-to-head comparison on the motor-lag env.

SAC is off-policy (replay buffer + gradient step per transition). Reward normalization
is OFF (recommended for off-policy). Obs are normalized + frame-stacked so the
memoryless policy can infer the hidden state (motor lag, wind, mass) from history.

Examples
--------
    python train_sac.py --smoke
    python train_sac.py --timesteps 500000 --n-envs 4 --n-stack 4
"""
import argparse
import os
import json

from stable_baselines3 import SAC
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import (SubprocVecEnv, DummyVecEnv,
                                              VecNormalize, VecFrameStack)

from rate_vel_aviary import RateVelAviary
from progress_callback import ProgressPlotCallback


def make_env_kwargs():
    return dict(episode_len_sec=8.0, max_speed=20.0)


def build_stacked(n_envs, seed, subproc, n_stack, training):
    # VecNormalize OUTSIDE VecFrameStack so off-policy get_original_obs() is stacked.
    cls = SubprocVecEnv if (subproc and n_envs > 1) else DummyVecEnv
    venv = make_vec_env(RateVelAviary, n_envs=n_envs, seed=seed,
                        env_kwargs=make_env_kwargs(), vec_env_cls=cls)
    if n_stack > 1:
        venv = VecFrameStack(venv, n_stack=n_stack)
    env = VecNormalize(venv, norm_obs=True, norm_reward=False,
                       clip_obs=10.0, training=training)
    return env, env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timesteps", type=int, default=500_000)
    ap.add_argument("--n-envs", type=int, default=4)
    ap.add_argument("--n-stack", type=int, default=4)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", type=str, default="results_sac_fs")
    ap.add_argument("--no-subproc", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    if args.smoke:
        args.timesteps, args.n_envs = 15_000, 2
    os.makedirs(args.out_dir, exist_ok=True)
    json.dump({"n_stack": args.n_stack}, open(os.path.join(args.out_dir, "config.json"), "w"))

    train_env, train_norm = build_stacked(args.n_envs, args.seed, not args.no_subproc,
                                          args.n_stack, training=True)
    eval_env, _ = build_stacked(1, args.seed + 999, not args.no_subproc,
                                args.n_stack, training=False)

    learning_starts = 5_000 if args.smoke else 10_000
    model = SAC(
        "MlpPolicy", train_env,
        learning_rate=3e-4, buffer_size=400_000,   # 88-dim stacked obs -> keep buffer modest
        learning_starts=learning_starts, batch_size=256,
        tau=0.005, gamma=0.99,
        train_freq=(1, "step"), gradient_steps=args.n_envs,
        ent_coef="auto",
        policy_kwargs=dict(net_arch=[128, 128]),
        tensorboard_log=os.path.join(args.out_dir, "tb"),
        seed=args.seed, verbose=1,
    )

    evalcb = ProgressPlotCallback(
        eval_env, out_dir=args.out_dir, tag="SAC+FS",
        best_model_save_path=os.path.join(args.out_dir, "best"),
        log_path=os.path.join(args.out_dir, "eval"),
        eval_freq=max(50_000 // args.n_envs, 1),
        n_eval_episodes=10, deterministic=True, render=False)

    model.learn(total_timesteps=args.timesteps, callback=evalcb, progress_bar=True)

    model.save(os.path.join(args.out_dir, "sac_ratevel_final"))
    train_norm.save(os.path.join(args.out_dir, "vecnormalize.pkl"))
    print(f"[DONE] saved SAC model + vecnormalize (+config n_stack={args.n_stack}) to {args.out_dir}/")
    train_env.close(); eval_env.close()


if __name__ == "__main__":
    main()
