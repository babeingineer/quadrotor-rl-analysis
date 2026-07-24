"""Train a PPO policy for 3-D velocity tracking on RateVelAviary.

The policy commands collective-thrust + body-rate (CTBR); a PID inner loop tracks
the rates. Obs are normalized (VecNormalize) and frame-stacked (VecFrameStack) so a
memoryless MLP can infer the hidden state (motor-lag spin-up, wind, mass) from recent
history.

Examples
--------
    python train.py --smoke                       # quick wiring test
    python train.py --timesteps 3000000 --n-envs 6 --n-stack 4
"""
import argparse
import os
import json

from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import (SubprocVecEnv, DummyVecEnv,
                                              VecNormalize, VecFrameStack)
from stable_baselines3.common.callbacks import CheckpointCallback

from rate_vel_aviary import RateVelAviary
from progress_callback import ProgressPlotCallback


def build_stacked(n_envs, seed, subproc, n_stack, norm_reward, training, env_kwargs):
    """VecNormalize(VecFrameStack(vec env)) — norm OUTSIDE stack so off-policy
    get_original_obs() returns the stacked obs. Returns (env, vecnormalize_handle)."""
    cls = SubprocVecEnv if (subproc and n_envs > 1) else DummyVecEnv
    venv = make_vec_env(RateVelAviary, n_envs=n_envs, seed=seed,
                        env_kwargs=env_kwargs, vec_env_cls=cls)
    if n_stack > 1:
        venv = VecFrameStack(venv, n_stack=n_stack)
    env = VecNormalize(venv, norm_obs=True, norm_reward=norm_reward,
                       clip_obs=10.0, gamma=0.99, training=training)
    return env, env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timesteps", type=int, default=3_000_000)
    ap.add_argument("--n-envs", type=int, default=6)
    ap.add_argument("--n-stack", type=int, default=1,
                    help="observation frames to stack (1 = none; motor RPM + wind observer "
                         "are fed directly, so stacking is redundant)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", type=str, default="results_fs")
    ap.add_argument("--task", type=str, default="velocity", choices=["velocity", "position"])
    ap.add_argument("--pos-range", type=float, default=30.0,
                    help="position task: target radius (m). Sets max cruise speed ~sqrt(a*R).")
    ap.add_argument("--speed-cap", type=float, default=18.0, help="position task: soft speed cap (m/s)")
    ap.add_argument("--no-subproc", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    if args.smoke:
        args.timesteps, args.n_envs = 20_000, 2
    os.makedirs(args.out_dir, exist_ok=True)
    json.dump({"n_stack": args.n_stack, "task": args.task,
               "pos_range": args.pos_range, "speed_cap": args.speed_cap},
              open(os.path.join(args.out_dir, "config.json"), "w"))

    base_kwargs = dict(task=args.task, episode_len_sec=8.0, max_speed=80.0,
                       pos_range=args.pos_range, speed_cap=args.speed_cap)
    train_kwargs = dict(base_kwargs, randomize_init=True)    # explore inversion/dive/high-speed
    eval_kwargs = dict(base_kwargs, randomize_init=False)    # standard hover start -> comparable metric
    train_env, train_norm = build_stacked(args.n_envs, args.seed, not args.no_subproc,
                                          args.n_stack, True, True, train_kwargs)
    eval_env, _ = build_stacked(1, args.seed + 999, not args.no_subproc,
                                args.n_stack, False, False, eval_kwargs)

    model = PPO(
        "MlpPolicy", train_env,
        n_steps=2048, batch_size=4096, n_epochs=10,
        gamma=0.99, gae_lambda=0.95, clip_range=0.2,
        ent_coef=0.0, learning_rate=3e-4, max_grad_norm=0.5,
        policy_kwargs=dict(net_arch=[256, 256]),
        tensorboard_log=os.path.join(args.out_dir, "tb"),
        seed=args.seed, verbose=1,
    )

    ckpt = CheckpointCallback(save_freq=max(100_000 // args.n_envs, 1),
                              save_path=os.path.join(args.out_dir, "ckpts"),
                              name_prefix="ppo_ratevel")
    evalcb = ProgressPlotCallback(
        eval_env, out_dir=args.out_dir, tag=f"PPO-{args.task}",
        best_model_save_path=os.path.join(args.out_dir, "best"),
        log_path=os.path.join(args.out_dir, "eval"),
        eval_freq=max(50_000 // args.n_envs, 1),
        n_eval_episodes=10, deterministic=True, render=False)

    model.learn(total_timesteps=args.timesteps, callback=[ckpt, evalcb], progress_bar=True)

    model.save(os.path.join(args.out_dir, "ppo_ratevel_final"))
    train_norm.save(os.path.join(args.out_dir, "vecnormalize.pkl"))
    print(f"[DONE] saved PPO model + vecnormalize (+config n_stack={args.n_stack}) to {args.out_dir}/")
    train_env.close(); eval_env.close()


if __name__ == "__main__":
    main()
