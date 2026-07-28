"""Continue training an existing PPO policy for more timesteps (same net/reward/env).
Loads the saved model + VecNormalize stats and resumes (optimizer state included).

    python continue_train.py --src results_pos3 --out results_pos3b --extra 3000000
"""
import argparse, json, os
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv, VecNormalize, VecFrameStack
from stable_baselines3.common.callbacks import CheckpointCallback
from rate_vel_aviary import RateVelAviary
from progress_callback import ProgressPlotCallback, DiveCurriculumCallback


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="results_pos3")
    ap.add_argument("--out", default="results_pos3b")
    ap.add_argument("--extra", type=int, default=3_000_000)
    ap.add_argument("--n-envs", type=int, default=6)
    ap.add_argument("--dive-curriculum", action="store_true",
                    help="ramp downward-dive difficulty (shallow->steep) over 75%% of --extra")
    ap.add_argument("--episode-len", type=float, default=8.0,
                    help="training episode length (s); longer lets the leaky integral fully settle")
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(args.src, "config.json")))
    n_stack = cfg.get("n_stack", 1)
    ui = cfg.get("use_integral", False)   # must match the saved model's obs dim
    uw = cfg.get("use_wind_est", True)
    base_kwargs = dict(task=cfg.get("task", "velocity"), episode_len_sec=args.episode_len, max_speed=80.0,
                       pos_range=cfg.get("pos_range", 30.0), speed_cap=cfg.get("speed_cap", 18.0),
                       use_wind_est=uw)
    train_kwargs = dict(base_kwargs, randomize_init=True, hard_corner_frac=0.0, use_vel_integral=ui,
                        dive_curriculum=args.dive_curriculum)
    eval_kwargs = dict(base_kwargs, randomize_init=False, hard_corner_frac=0.0, use_vel_integral=ui)
    os.makedirs(args.out, exist_ok=True)
    json.dump(cfg, open(os.path.join(args.out, "config.json"), "w"))

    def norm_env(n, seed, train, nr, ekw):
        v = make_vec_env(RateVelAviary, n_envs=n, seed=seed, env_kwargs=ekw,
                         vec_env_cls=SubprocVecEnv if n > 1 else DummyVecEnv)
        if n_stack > 1:
            v = VecFrameStack(v, n_stack=n_stack)          # VecNormalize OUTSIDE the stack
        v = VecNormalize.load(os.path.join(args.src, "vecnormalize.pkl"), v)
        v.training = train; v.norm_reward = nr
        return v

    train_env = norm_env(args.n_envs, 0, True, True, train_kwargs)
    eval_env = norm_env(1, 999, False, False, eval_kwargs)

    model = PPO.load(os.path.join(args.src, "ppo_ratevel_final.zip"), env=train_env)
    print(f"[RESUME] loaded {args.src} at {model.num_timesteps:,} steps; training +{args.extra:,}")

    ckpt = CheckpointCallback(save_freq=max(100_000 // args.n_envs, 1),
                              save_path=os.path.join(args.out, "ckpts"), name_prefix="ppo_ratevel")
    evalcb = ProgressPlotCallback(
        eval_env, out_dir=args.out, tag=f"PPO-{cfg.get('task', 'velocity')}(cont)",
        best_model_save_path=os.path.join(args.out, "best"),
        log_path=os.path.join(args.out, "eval"),
        eval_freq=max(50_000 // args.n_envs, 1),
        n_eval_episodes=10, deterministic=True, render=False)

    cbs = [ckpt, evalcb]
    if args.dive_curriculum:
        cbs.append(DiveCurriculumCallback(ramp_steps=int(0.75 * args.extra), verbose=1))
    model.learn(total_timesteps=args.extra, reset_num_timesteps=False,
                callback=cbs, progress_bar=True)
    model.save(os.path.join(args.out, "ppo_ratevel_final"))
    train_env.save(os.path.join(args.out, "vecnormalize.pkl"))
    print(f"[DONE] continued to {model.num_timesteps:,} steps, saved to {args.out}/")
    train_env.close(); eval_env.close()


if __name__ == "__main__":
    main()
