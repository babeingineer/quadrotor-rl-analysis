"""Train a RECURRENT PPO (LSTM) policy on RateVelAviary velocity task.

Same env / reward / VecNormalize / domain-randomization as train.py, but an LSTM policy
(sb3_contrib.RecurrentPPO) supplies learned temporal memory instead of frame-stacking.
n_stack is forced to 1 (the LSTM IS the memory). Saves best_model + vecnormalize like train.py
so eval_mem.py can load it. config.json marks algo="recurrent_ppo".
"""
import argparse, os, json
from sb3_contrib import RecurrentPPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv, VecNormalize
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback
from rate_vel_aviary import RateVelAviary


def build_env(n_envs, seed, subproc, training, env_kwargs):
    cls = SubprocVecEnv if (subproc and n_envs > 1) else DummyVecEnv
    venv = make_vec_env(RateVelAviary, n_envs=n_envs, seed=seed, env_kwargs=env_kwargs, vec_env_cls=cls)
    venv = VecNormalize(venv, norm_obs=True, norm_reward=training, clip_obs=10.0, gamma=0.99,
                        training=training)
    return venv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timesteps", type=int, default=8_000_000)
    ap.add_argument("--n-envs", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", type=str, default="results_m_lstm")
    ap.add_argument("--use-integral", action="store_true")
    ap.add_argument("--no-wind-est", action="store_true")
    ap.add_argument("--no-subproc", action="store_true")
    args = ap.parse_args()

    use_wind_est = not args.no_wind_est
    os.makedirs(args.out_dir, exist_ok=True)
    json.dump({"n_stack": 1, "task": "velocity", "pos_range": 30.0, "speed_cap": 18.0,
               "use_integral": args.use_integral, "use_wind_est": use_wind_est, "algo": "recurrent_ppo"},
              open(os.path.join(args.out_dir, "config.json"), "w"))

    base_kwargs = dict(task="velocity", episode_len_sec=8.0, max_speed=80.0, use_wind_est=use_wind_est)
    train_kwargs = dict(base_kwargs, randomize_init=True, use_vel_integral=args.use_integral)
    eval_kwargs = dict(base_kwargs, randomize_init=False, use_vel_integral=args.use_integral)

    train_env = build_env(args.n_envs, args.seed, not args.no_subproc, True, train_kwargs)
    eval_env = build_env(1, args.seed + 999, not args.no_subproc, False, eval_kwargs)

    model = RecurrentPPO(
        "MlpLstmPolicy", train_env,
        n_steps=2048, batch_size=4096, n_epochs=10,           # 4096 | 6*2048=12288 -> 3 minibatches
        gamma=0.99, gae_lambda=0.95, clip_range=0.2,
        ent_coef=0.0, learning_rate=3e-4, max_grad_norm=0.5,
        policy_kwargs=dict(net_arch=[256, 256], lstm_hidden_size=256),
        tensorboard_log=os.path.join(args.out_dir, "tb"), seed=args.seed, verbose=1,
    )

    ckpt = CheckpointCallback(save_freq=max(200_000 // args.n_envs, 1),
                              save_path=os.path.join(args.out_dir, "ckpts"), name_prefix="lstm")
    evalcb = EvalCallback(eval_env, best_model_save_path=os.path.join(args.out_dir, "best"),
                          log_path=os.path.join(args.out_dir, "eval"),
                          eval_freq=max(50_000 // args.n_envs, 1),
                          n_eval_episodes=10, deterministic=True, render=False)

    model.learn(total_timesteps=args.timesteps, callback=[ckpt, evalcb], progress_bar=True)
    model.save(os.path.join(args.out_dir, "lstm_ratevel_final"))
    train_env.save(os.path.join(args.out_dir, "vecnormalize.pkl"))
    print(f"[DONE] LSTM saved to {args.out_dir}/")
    train_env.close(); eval_env.close()


if __name__ == "__main__":
    main()
