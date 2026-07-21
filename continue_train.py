"""Continue training an existing PPO policy for more timesteps (same net/reward/env).
Loads the saved model + VecNormalize stats and resumes (optimizer state included).

    python continue_train.py --src results_pos3 --out results_pos3b --extra 3000000
"""
import argparse, json, os
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv, VecNormalize
from stable_baselines3.common.callbacks import CheckpointCallback
from rate_vel_aviary import RateVelAviary
from progress_callback import ProgressPlotCallback


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="results_pos3")
    ap.add_argument("--out", default="results_pos3b")
    ap.add_argument("--extra", type=int, default=3_000_000)
    ap.add_argument("--n-envs", type=int, default=6)
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(args.src, "config.json")))
    assert cfg.get("n_stack", 1) == 1
    ekw = dict(task=cfg.get("task", "velocity"), episode_len_sec=8.0, max_speed=20.0,
               pos_range=cfg.get("pos_range", 30.0), speed_cap=cfg.get("speed_cap", 18.0))
    os.makedirs(args.out, exist_ok=True)
    json.dump(cfg, open(os.path.join(args.out, "config.json"), "w"))

    def norm_env(n, seed, train, nr):
        v = make_vec_env(RateVelAviary, n_envs=n, seed=seed, env_kwargs=ekw,
                         vec_env_cls=SubprocVecEnv if n > 1 else DummyVecEnv)
        v = VecNormalize.load(os.path.join(args.src, "vecnormalize.pkl"), v)
        v.training = train; v.norm_reward = nr
        return v

    train_env = norm_env(args.n_envs, 0, True, True)
    eval_env = norm_env(1, 999, False, False)

    model = PPO.load(os.path.join(args.src, "ppo_ratevel_final.zip"), env=train_env)
    print(f"[RESUME] loaded {args.src} at {model.num_timesteps:,} steps; training +{args.extra:,}")

    ckpt = CheckpointCallback(save_freq=max(100_000 // args.n_envs, 1),
                              save_path=os.path.join(args.out, "ckpts"), name_prefix="ppo_ratevel")
    evalcb = ProgressPlotCallback(
        eval_env, out_dir=args.out, tag=f"PPO-{ekw['task']}(cont)",
        best_model_save_path=os.path.join(args.out, "best"),
        log_path=os.path.join(args.out, "eval"),
        eval_freq=max(50_000 // args.n_envs, 1),
        n_eval_episodes=10, deterministic=True, render=False)

    model.learn(total_timesteps=args.extra, reset_num_timesteps=False,
                callback=[ckpt, evalcb], progress_bar=True)
    model.save(os.path.join(args.out, "ppo_ratevel_final"))
    train_env.save(os.path.join(args.out, "vecnormalize.pkl"))
    print(f"[DONE] continued to {model.num_timesteps:,} steps, saved to {args.out}/")
    train_env.close(); eval_env.close()


if __name__ == "__main__":
    main()
