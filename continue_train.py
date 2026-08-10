"""Continue training an existing velyaw PPO policy from an explicit checkpoint pair.
Loads matching model + VecNormalize state and resumes (optimizer state included).

    python continue_train.py --src results_velyaw --source-checkpoint best \
        --out results_velyaw2 --extra 4000000
"""
import argparse, json, os
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv, VecNormalize
from stable_baselines3.common.callbacks import CheckpointCallback
from rate_vel_aviary import RateVelAviary
from progress_callback import ProgressPlotCallback
from checkpoint_utils import resolve_checkpoint, sha256_file, write_checkpoint_manifest


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
    ap.add_argument("--att-tilt-ext", type=float, default=None,
                    help="resolution-preserving tilt extension (deg): legacy map for "
                         "|xy|<=0.9, outer 10%% of the ball reaches this. ACTION-SEMANTICS "
                         "change above 0.9, so expect some re-adaptation on continuation")
    ap.add_argument("--rel-basin", type=float, default=None,
                    help="set the command-scaled approach-basin weight only")
    ap.add_argument("--cmd-linear", action="store_true",
                    help="enable the command-keyed far-field linear pull only")
    ap.add_argument("--source-checkpoint", choices=("best", "final"), default=None,
                    help="required unless explicit model and VecNormalize files are supplied")
    ap.add_argument("--model-file", type=str, default=None,
                    help="explicit model zip; requires --vecnormalize-file")
    ap.add_argument("--vecnormalize-file", type=str, default=None,
                    help="normalization state paired with --model-file")
    ap.add_argument("--wind-oversample", type=float, default=None,
                    help="set/override strong-wind episode oversampling for this continuation "
                         "(training-distribution change: safe on continuation)")
    ap.add_argument("--tough-init-override", type=float, default=None,
                    help="set/override the failure-state (upset) init fraction for this "
                         "continuation — recovery curriculum without touching the recipe")
    ap.add_argument("--integral-tau-override", type=float, default=None,
                    help="change the velocity-integral leak for this continuation (obs "
                         "DYNAMICS change: values shift meaning, so expect re-adaptation)")
    ap.add_argument("--yaw-integral-tau-override", type=float, default=None,
                    help="change the yaw-integral leak for this continuation")
    ap.add_argument("--max-speed-override", type=float, default=None,
                    help="widen the target-speed envelope for this continuation (band-extension "
                         "transfer); obs scaling uses the same MAX_SPEED so update config too")
    ap.add_argument("--speed-min-override", type=float, default=None)
    args = ap.parse_args()

    if args.source_checkpoint is None and args.model_file is None:
        ap.error("choose --source-checkpoint best|final, or supply both --model-file and "
                 "--vecnormalize-file")
    if args.source_checkpoint is not None and args.model_file is not None:
        ap.error("use either --source-checkpoint or explicit model/VecNormalize files, not both")
    model_file, vecnormalize_file, source_label = resolve_checkpoint(
        args.src, checkpoint=args.source_checkpoint or "auto",
        model_file=args.model_file, vecnormalize_file=args.vecnormalize_file)

    cfg = json.load(open(os.path.join(args.src, "config.json")))
    if args.vel_precision is not None:
        cfg["vel_precision"] = args.vel_precision      # reward-only change: safe on continuation
    if args.yaw_att_gate:
        cfg["yaw_att_gate"] = True                     # reward-only change: safe on continuation
    if args.cov_width is not None:
        cfg["cov_width"] = args.cov_width              # reward-only change: safe on continuation
    if args.att_tilt_ext is not None:
        cfg["att_tilt_ext"] = args.att_tilt_ext
    if args.rel_basin is not None:
        cfg["rel_basin"] = args.rel_basin
    if args.cmd_linear:
        cfg["cmd_linear"] = True
    if args.yaw_bias is not None:
        cfg["yaw_bias"] = args.yaw_bias
    if args.wind_oversample is not None:
        cfg["wind_oversample"] = args.wind_oversample
    if args.tough_init_override is not None:
        cfg["tough_init"] = args.tough_init_override
    if args.integral_tau_override is not None:
        cfg["integral_tau"] = args.integral_tau_override
    if args.yaw_integral_tau_override is not None:
        cfg["yaw_integral_tau"] = args.yaw_integral_tau_override
    if args.max_speed_override is not None:
        cfg["max_speed"] = args.max_speed_override
    if args.speed_min_override is not None:
        cfg["speed_min"] = args.speed_min_override
    cfg["episode_len"] = args.episode_len

    # Apply every override to cfg BEFORE constructing the environments. The historical order
    # built base_kwargs first, so max/speed-min and integral overrides were one stage stale.
    base_kwargs = dict(episode_len_sec=cfg["episode_len"],
                       max_speed=cfg.get("max_speed", 25.0),
                       speed_min=cfg.get("speed_min", 0.0),
                       target_speed_max=cfg.get("target_speed_max", None),
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
                       att_tilt_max=cfg.get("att_tilt_max", 0.0),
                       att_tilt_ext=cfg.get("att_tilt_ext", 0.0),
                       rel_obs=cfg.get("rel_obs", False),
                       rel_approach=cfg.get("rel_approach", 0.0),
                       rel_basin=cfg.get("rel_basin", 0.0),
                       cmd_linear=cfg.get("cmd_linear", False),
                       rel_width=cfg.get("rel_width", 0.5),
                       rel_floor=cfg.get("rel_floor", 8.0),
                       yaw_att_gate=cfg.get("yaw_att_gate", False),
                       cov_width=cfg.get("cov_width", 0.0),
                       aero_dr=cfg.get("aero_dr", True),
                       integral_tau=cfg.get("integral_tau", 3.0),
                       yaw_integral_tau=cfg.get("yaw_integral_tau", None),
                       priv_obs=cfg.get("priv_critic", False),
                       att_cmd=cfg.get("att_cmd", False), katt=cfg.get("katt", 1.5),
                       att_rel=cfg.get("att_rel", False), att_rel_k=cfg.get("att_rel_k", 0.5),
                       trim_ff=cfg.get("trim_ff", False), trim_ff_k=cfg.get("trim_ff_k", 0.4),
                       trim_ff_thrust=cfg.get("trim_ff_thrust", 0.4),
                       trim_ff_fin=cfg.get("trim_ff_fin", 0.5),
                       trim_ff_true_wind=cfg.get("trim_ff_true_wind", True),
                       ctrl_freq=cfg.get("ctrl_freq", 50),
                       fin_assist=cfg.get("fin_assist", 0.0),
                       air_obs=cfg.get("air_obs", False),
                       kp_rate=tuple(float(x) for x in cfg.get("kp_rate", "6,6,4").split(",")),
                       ki_rate=tuple(float(x) for x in cfg.get("ki_rate", "0.5,0.5,0.3").split(",")))
    print(f"[ENV CONFIG] speed={base_kwargs['speed_min']:.3g}–"
          f"{base_kwargs['max_speed']:.3g} m/s, integral_tau="
          f"{base_kwargs['integral_tau']:.3g}, yaw_integral_tau="
          f"{base_kwargs['yaw_integral_tau']}, episode={base_kwargs['episode_len_sec']:.3g} s")
    # same tough/trim-init mix as the source run; wind stays at the full post-curriculum value
    train_kwargs = dict(base_kwargs, randomize_init=True,
                        tough_init_frac=cfg.get("tough_init", 0.0),
                        trim_init_frac=cfg.get("trim_init", 0.0),
                        wind_oversample=cfg.get("wind_oversample", 0.0))
    eval_kwargs = dict(base_kwargs, randomize_init=False)
    os.makedirs(args.out, exist_ok=True)

    def norm_env(n, seed, train, nr, ekw):
        cls = SubprocVecEnv if n > 1 else DummyVecEnv
        v = make_vec_env(RateVelAviary, n_envs=n, seed=seed, env_kwargs=ekw, vec_env_cls=cls)
        v = VecNormalize.load(vecnormalize_file, v)
        v.training = train; v.norm_reward = nr
        return v

    train_env = norm_env(args.n_envs, 0, True, True, train_kwargs)
    eval_env = norm_env(1, 999, False, False, eval_kwargs)

    co = {"learning_rate": args.lr} if args.lr is not None else {}
    if cfg.get("algo") == "recurrent_ppo":
        from sb3_contrib import RecurrentPPO
        model = RecurrentPPO.load(model_file, env=train_env, device=args.device, custom_objects=co)
    else:
        model = PPO.load(model_file, env=train_env, device=args.device, custom_objects=co)
    # SB3 serializes tensorboard_log inside the model. Without this override a continuation can
    # append telemetry to an ancestor run, making the destination's curve incomplete/misleading.
    model.tensorboard_log = os.path.join(args.out, "tb")
    cfg["lineage"] = {
        "source_dir": os.path.abspath(args.src),
        "source_checkpoint": source_label,
        "source_timestep": int(model.num_timesteps),
        "source_model_sha256": sha256_file(model_file),
        "source_vecnormalize_sha256": sha256_file(vecnormalize_file),
    }
    with open(os.path.join(args.out, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, sort_keys=True)
        f.write("\n")
    print(f"[RESUME] loaded {source_label} pair from {args.src} at "
          f"{model.num_timesteps:,} steps; training +{args.extra:,}")

    ckpt = CheckpointCallback(save_freq=max(100_000 // args.n_envs, 1),
                              save_path=os.path.join(args.out, "ckpts"),
                              name_prefix="ppo_ratevel", save_vecnormalize=True)
    evalcb = ProgressPlotCallback(
        eval_env, out_dir=args.out, tag="PPO-velyaw(cont)",
        best_model_save_path=os.path.join(args.out, "best"),
        log_path=os.path.join(args.out, "eval"),
        eval_freq=max(50_000 // args.n_envs, 1),
        n_eval_episodes=10, deterministic=True, render=False)

    model.learn(total_timesteps=args.extra, reset_num_timesteps=False,
                callback=[ckpt, evalcb], progress_bar=True)
    model.save(os.path.join(args.out, "ppo_ratevel_final"))
    train_env.save(os.path.join(args.out, "vecnormalize.pkl"))
    write_checkpoint_manifest(
        args.out, os.path.join(args.out, "ppo_ratevel_final.zip"),
        os.path.join(args.out, "vecnormalize.pkl"), model.num_timesteps,
        manifest_name="checkpoint_final.json")
    print(f"[DONE] continued to {model.num_timesteps:,} steps, saved to {args.out}/")
    train_env.close(); eval_env.close()


if __name__ == "__main__":
    main()
