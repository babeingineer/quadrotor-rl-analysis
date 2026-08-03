"""Continue training an existing velyaw PPO policy for more timesteps (same net/reward/env).
Loads the saved model + VecNormalize stats and resumes (optimizer state included).

    python continue_train.py --src results_velyaw --out results_velyaw2 --extra 4000000
"""
import argparse, json, os
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv, VecNormalize
from stable_baselines3.common.callbacks import CheckpointCallback, BaseCallback
from rate_vel_aviary import RateVelAviary
from progress_callback import ProgressPlotCallback


class VecNormSaveCallback(BaseCallback):
    """Save VecNormalize stats on the checkpoint cadence so a killed run can resume
    consistently (model ckpt + matching obs-normalization stats)."""
    def __init__(self, env, path, every):
        super().__init__(); self.env = env; self.path = path; self.every = every; self._last = 0

    def _on_step(self):
        if self.num_timesteps - self._last >= self.every:
            self.env.save(self.path); self._last = self.num_timesteps
        return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="results_velyaw")
    ap.add_argument("--out", default="results_velyaw2")
    ap.add_argument("--extra", type=int, default=4_000_000)
    ap.add_argument("--n-envs", type=int, default=6)
    ap.add_argument("--episode-len", type=float, default=8.0)
    ap.add_argument("--yaw-bias", type=float, default=None,
                    help="override the per-episode yaw-torque disturbance (default: from config)")
    ap.add_argument("--device", type=str, default="cpu")
    ap.add_argument("--lr", type=float, default=None,
                    help="override learning rate for the continuation (fine-tune)")
    ap.add_argument("--vel-precision", type=float, default=None,
                    help="set/override the narrow velocity precision peak weight")
    ap.add_argument("--yaw-att-gate", action="store_true",
                    help="enable the attitude gate on the yaw reward for this continuation")
    ap.add_argument("--cov-width", type=float, default=None,
                    help="set/override the coverage Gaussian width (m/s)")
    ap.add_argument("--model-file", type=str, default=None,
                    help="explicit model zip to resume from (default src/ppo_ratevel_final.zip)")
    ap.add_argument("--wind-oversample", type=float, default=None,
                    help="set/override strong-wind episode oversampling for this continuation "
                         "(training-distribution change: safe on continuation)")
    ap.add_argument("--max-speed-override", type=float, default=None,
                    help="widen the target-speed envelope for this continuation (band-extension "
                         "transfer); obs scaling uses the same MAX_SPEED so update config too")
    ap.add_argument("--speed-min-override", type=float, default=None)
    args = ap.parse_args()

    cfg = json.load(open(os.path.join(args.src, "config.json")))
    if args.vel_precision is not None:
        cfg["vel_precision"] = args.vel_precision      # reward-only change: safe on continuation
    if args.yaw_att_gate:
        cfg["yaw_att_gate"] = True                     # reward-only change: safe on continuation
    if args.cov_width is not None:
        cfg["cov_width"] = args.cov_width              # reward-only change: safe on continuation
    yaw_bias = cfg.get("yaw_bias", 0.0) if args.yaw_bias is None else args.yaw_bias
    # obs-affecting flags MUST match the saved model; reward/DR params carry over from config.
    base_kwargs = dict(episode_len_sec=args.episode_len, max_speed=cfg.get("max_speed", 25.0),
                       speed_min=cfg.get("speed_min", 0.0),
                       wind_max=cfg.get("wind_max", 20.0),
                       use_wind_est=cfg.get("use_wind_est", True),
                       use_vel_integral=cfg.get("use_integral", True),
                       use_yaw_integral=cfg.get("use_yaw_integral", True),
                       yaw_reward_width=cfg.get("yaw_width", 0.35),
                       yaw_weight=cfg.get("yaw_weight", 1.0), yaw_bias_max=yaw_bias,
                       velyaw_heading_frame=cfg.get("heading_frame", False),
                       use_xwing_aero=cfg.get("xwing_aero", False),
                       yaw_gate=cfg.get("yaw_gate", False),
                       yaw_gate_floor=cfg.get("yaw_gate_floor", 0.2),
                       vel_precision=cfg.get("vel_precision", 0.0),
                       yaw_att_gate=cfg.get("yaw_att_gate", False),
                       cov_width=cfg.get("cov_width", 0.0),
                       aero_dr=cfg.get("aero_dr", True),
                       integral_tau=cfg.get("integral_tau", 3.0),
                       priv_obs=cfg.get("priv_critic", False),
                       att_cmd=cfg.get("att_cmd", False), katt=cfg.get("katt", 1.5),
                       ctrl_freq=cfg.get("ctrl_freq", 50),
                       fin_assist=cfg.get("fin_assist", 0.0),
                       air_obs=cfg.get("air_obs", False),
                       kp_rate=tuple(float(x) for x in cfg.get("kp_rate", "6,6,4").split(",")),
                       ki_rate=tuple(float(x) for x in cfg.get("ki_rate", "0.5,0.5,0.3").split(",")))
    if args.wind_oversample is not None:
        cfg["wind_oversample"] = args.wind_oversample
    if args.max_speed_override is not None:
        cfg["max_speed"] = args.max_speed_override
    if args.speed_min_override is not None:
        cfg["speed_min"] = args.speed_min_override
    # same tough/trim-init mix as the source run; wind stays at the full post-curriculum value
    train_kwargs = dict(base_kwargs, randomize_init=True,
                        tough_init_frac=cfg.get("tough_init", 0.0),
                        trim_init_frac=cfg.get("trim_init", 0.0),
                        wind_oversample=cfg.get("wind_oversample", 0.0))
    eval_kwargs = dict(base_kwargs, randomize_init=False)
    os.makedirs(args.out, exist_ok=True)
    json.dump(cfg, open(os.path.join(args.out, "config.json"), "w"))

    def norm_env(n, seed, train, nr, ekw):
        cls = SubprocVecEnv if n > 1 else DummyVecEnv
        v = make_vec_env(RateVelAviary, n_envs=n, seed=seed, env_kwargs=ekw, vec_env_cls=cls)
        v = VecNormalize.load(os.path.join(args.src, "vecnormalize.pkl"), v)
        v.training = train; v.norm_reward = nr
        return v

    train_env = norm_env(args.n_envs, 0, True, True, train_kwargs)
    eval_env = norm_env(1, 999, False, False, eval_kwargs)

    co = {"learning_rate": args.lr} if args.lr is not None else {}
    mf = args.model_file or os.path.join(args.src, "ppo_ratevel_final.zip")
    if cfg.get("algo") == "recurrent_ppo":
        from sb3_contrib import RecurrentPPO
        model = RecurrentPPO.load(mf, env=train_env, device=args.device, custom_objects=co)
    else:
        model = PPO.load(mf, env=train_env, device=args.device, custom_objects=co)
    print(f"[RESUME] loaded {args.src} at {model.num_timesteps:,} steps; training +{args.extra:,}")

    ckpt = CheckpointCallback(save_freq=max(100_000 // args.n_envs, 1),
                              save_path=os.path.join(args.out, "ckpts"), name_prefix="ppo_ratevel")
    evalcb = ProgressPlotCallback(
        eval_env, out_dir=args.out, tag="PPO-velyaw(cont)",
        best_model_save_path=os.path.join(args.out, "best"),
        log_path=os.path.join(args.out, "eval"),
        eval_freq=max(50_000 // args.n_envs, 1),
        n_eval_episodes=10, deterministic=True, render=False)

    vns = VecNormSaveCallback(train_env, os.path.join(args.out, "vecnormalize.pkl"),
                              every=100_000)
    model.learn(total_timesteps=args.extra, reset_num_timesteps=False,
                callback=[ckpt, evalcb, vns], progress_bar=True)
    model.save(os.path.join(args.out, "ppo_ratevel_final"))
    train_env.save(os.path.join(args.out, "vecnormalize.pkl"))
    print(f"[DONE] continued to {model.num_timesteps:,} steps, saved to {args.out}/")
    train_env.close(); eval_env.close()


if __name__ == "__main__":
    main()
