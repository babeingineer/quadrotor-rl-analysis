"""Train a PPO (MLP) policy for the velyaw task on RateVelAviary: track a target velocity AND
a commanded heading. The policy commands collective-thrust + body-rate (CTBR); a PID inner loop
tracks the rates. Obs are normalized (VecNormalize). Memoryless MLP — motor RPM, the wind
observer, and the leaky integrals are fed directly, so no frame-stack / LSTM is needed.

Examples
--------
    python train.py --smoke                                  # quick wiring test
    python train.py --timesteps 8000000 --n-envs 6 --yaw-bias 0.3
"""
import argparse
import os
import json

from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import SubprocVecEnv, DummyVecEnv, VecNormalize
from stable_baselines3.common.callbacks import CheckpointCallback, BaseCallback

from rate_vel_aviary import RateVelAviary
from progress_callback import ProgressPlotCallback
from checkpoint_utils import write_checkpoint_manifest


class WindCurriculumCallback(BaseCallback):
    """Ramp per-episode wind: WIND_MAX = w0 until `start` steps, linear to w1 by `end`.
    The eval env stays at full wind so the metric tracks the real task throughout."""
    def __init__(self, w0, w1, start, end, verbose=0):
        super().__init__(verbose)
        self.w0, self.w1, self.start, self.end = w0, w1, start, end
        self._last = None

    def _on_rollout_start(self):
        t = self.model.num_timesteps
        frac = min(max((t - self.start) / max(self.end - self.start, 1), 0.0), 1.0)
        w = self.w0 + frac * (self.w1 - self.w0)
        if self._last is None or abs(w - self._last) > 0.05:
            self.training_env.env_method("set_wind_max", w)
            self._last = w
            if self.verbose:
                print(f"[wind curriculum] step {t:,}: wind_max = {w:.1f} m/s")

    def _on_step(self):
        return True


def norm_env(n_envs, seed, subproc, norm_reward, training, env_kwargs, norm_gamma=0.99):
    cls = SubprocVecEnv if (subproc and n_envs > 1) else DummyVecEnv
    venv = make_vec_env(RateVelAviary, n_envs=n_envs, seed=seed,
                        env_kwargs=env_kwargs, vec_env_cls=cls)
    env = VecNormalize(venv, norm_obs=True, norm_reward=norm_reward,
                       clip_obs=10.0, gamma=norm_gamma, training=training)
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timesteps", type=int, default=8_000_000)
    ap.add_argument("--n-envs", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", type=str, default="results_velyaw")
    ap.add_argument("--max-speed", type=float, default=25.0, help="velocity envelope (m/s)")
    ap.add_argument("--speed-min", type=float, default=0.0,
                    help="min target speed (band-limited specialist)")
    ap.add_argument("--wind-max", type=float, default=15.0,
                    help="per-episode wind is U(0, wind_max); real XWing spec = 15 m/s")
    ap.add_argument("--yaw-bias", type=float, default=0.0,
                    help="per-episode constant yaw-torque disturbance magnitude (N*m)")
    ap.add_argument("--yaw-weight", type=float, default=1.0, help="heading objective weight")
    ap.add_argument("--yaw-width", type=float, default=0.35, help="heading reward peak width (rad)")
    ap.add_argument("--heading-frame", action="store_true",
                    help="express the velocity error in the current-heading frame")
    ap.add_argument("--no-integral", action="store_true", help="drop the leaky velocity-error integral")
    ap.add_argument("--no-yaw-integral", action="store_true", help="drop the leaky yaw-error integral")
    ap.add_argument("--no-wind-est", action="store_true", help="drop the disturbance-observer wind estimate")
    ap.add_argument("--xwing-aero", action="store_true",
                    help="use the ported XWing aero model + XWing mass/inertia/motor power (S=C=b=1)")
    ap.add_argument("--tough-init", type=float, default=0.0,
                    help="fraction of TRAINING episodes started in failure states (dive/botched "
                         "transition) so recovery gets direct gradient")
    ap.add_argument("--trim-init", type=float, default=0.0,
                    help="fraction of TRAINING episodes started AT the target velocity in "
                         "near-trim attitude (trim_table.npz)")
    ap.add_argument("--att-cmd", action="store_true",
                    help="attitude-setpoint action interface (thrust + desired body-z + yaw "
                         "rate -> inner attitude P -> rate PID)")
    ap.add_argument("--katt", type=float, default=1.5, help="attitude-P gain for --att-cmd")
    ap.add_argument("--trim-ff", action="store_true",
                    help="TRIM FEEDFORWARD: solve the episode's trim once at reset; the "
                         "policy commands only the deviation from it (a=0 holds trim)")
    ap.add_argument("--trim-ff-k", type=float, default=0.4,
                    help="tilt deviation scale for --trim-ff (max ~atan(k))")
    ap.add_argument("--trim-ff-thrust", type=float, default=0.4,
                    help="thrust deviation span for --trim-ff, x NOMINAL_HOVER")
    ap.add_argument("--trim-ff-fin", type=float, default=0.5,
                    help="elevon deviation span for --trim-ff, x FIN_MAX")
    ap.add_argument("--trim-ff-est-wind", action="store_true",
                    help="index the feedforward trim with the observer's wind estimate "
                         "(deployable) instead of the true wind (privileged ceiling test)")
    ap.add_argument("--att-rel", action="store_true",
                    help="body-relative attitude command (constant conditioning at all tilts; "
                         "a=0 holds the current thrust axis)")
    ap.add_argument("--att-rel-k", type=float, default=0.5,
                    help="max per-step tilt correction = atan(k) for --att-rel")
    ap.add_argument("--fin-assist", type=float, default=0.0,
                    help="att-cmd: elevator follows the pitch-rate command with this gain "
                         "(fin authority scales with V^2; motor torque does not)")
    ap.add_argument("--ctrl-freq", type=int, default=50,
                    help="policy rate (Hz); physics stays 500 Hz. When raising this, rescale "
                         "gamma to keep the same TIME horizon (e.g. 50->100 Hz: 0.99->0.995)")
    ap.add_argument("--air-obs", action="store_true",
                    help="DIAGNOSTIC: actor observes true body-frame air-relative velocity "
                         "(3 dims); tests whether the strong-wind tail is an observability gap")
    ap.add_argument("--priv-critic", action="store_true",
                    help="asymmetric actor-critic: critic sees the hidden episode draw "
                         "(27 dims appended to obs); actor sees only the deployable obs "
                         "(priv_policy.py slices)")
    ap.add_argument("--wind-curriculum", action="store_true",
                    help="train wind_max: 8 m/s until 3M steps, linear ramp to 20 by 6M")
    ap.add_argument("--yaw-gate", action="store_true",
                    help="gate the yaw reward by velocity success (kills the yaw-only dive optimum)")
    ap.add_argument("--yaw-gate-floor", type=float, default=0.2,
                    help="fraction of the yaw reward that always pays (gate floor)")
    ap.add_argument("--ent-coef", type=float, default=0.0)
    ap.add_argument("--gae-lambda", type=float, default=0.95,
                    help="GAE lambda; rescale with ctrl rate to keep the same TIME window "
                         "(50->100 Hz: 0.95 -> 0.975)")
    ap.add_argument("--n-steps", type=int, default=2048,
                    help="PPO rollout length per env; double with ctrl rate to span the "
                         "same seconds")
    ap.add_argument("--gamma", type=float, default=0.99,
                    help="discount factor (0.99 at 50 Hz control = ~2 s value horizon)")
    ap.add_argument("--episode-len", type=float, default=8.0,
                    help="TRAINING episode length (s)")
    ap.add_argument("--cov-width", type=float, default=0.0,
                    help="coverage Gaussian width in m/s (0 = legacy 10*MAX_SPEED/20)")
    ap.add_argument("--vel-precision", type=float, default=0.0,
                    help="weight of the narrow (1-tanh(d/0.5)) velocity precision peak")
    ap.add_argument("--rel-approach", type=float, default=0.0,
                    help="DEPRECATED combined alias: enable both --rel-basin at this weight "
                         "and --cmd-linear. Absolute "
                         "reward widths go numerically dead far from a fast target (gradient "
                         "4e-22 at 50 m/s commanded) and the legacy linear pull is scaled by "
                         "20/MAX_SPEED, so widening the envelope weakens it. This adds a basin "
                         "whose width tracks the COMMANDED speed and keys the linear pull to it "
                         "too, leaving every absolute (goal) term untouched. Required to train "
                         "ONE policy over a wide range; try 1.0")
    ap.add_argument("--rel-obs", action="store_true",
                    help="add COMMAND-SCALED velocity error (3 dims) to the obs; the "
                         "absolute channel divides by MAX_SPEED and loses slow-speed "
                         "resolution over a wide envelope")
    ap.add_argument("--att-tilt-ext", type=float, default=0.0,
                    help="resolution-preserving tilt extension: legacy arcsin map for "
                         "|xy|<=0.9 (0-64 deg), outer 10%% of the ball reaches this max "
                         "tilt in degrees. Use instead of --att-tilt-max, which "
                         "rescales the whole map and was refuted in trial 78.")
    ap.add_argument("--att-tilt-max", type=float, default=0.0,
                    help="0 = legacy upper-hemisphere thrust axis (tilt capped at 80 deg); "
                         ">0 = full-sphere command with this max tilt in degrees. Steep "
                         "descents at speed need 82-93 deg, which the legacy encoding "
                         "cannot express at any action value.")
    ap.add_argument("--rel-basin", type=float, default=0.0,
                    help="weight of the command-scaled approach basin ONLY; use independently "
                         "from --cmd-linear for the trial-72 ablation")
    ap.add_argument("--cmd-linear", action="store_true",
                    help="key the far-field linear pull to commanded speed ONLY")
    ap.add_argument("--rel-width", type=float, default=0.5,
                    help="approach-basin width as a fraction of commanded speed")
    ap.add_argument("--rel-floor", type=float, default=8.0,
                    help="commanded-speed floor (m/s) so hover/low keeps sane widths")
    ap.add_argument("--yaw-att-gate", action="store_true",
                    help="release the yaw reward in wing-borne flight (clip(R22,0,1) gate)")
    ap.add_argument("--integral-tau", type=float, default=3.0,
                    help="velocity/yaw integral leak time constant (s); very large (1e6) "
                         "approximates a true integrator")
    ap.add_argument("--yaw-integral-tau", type=float, default=None,
                    help="separate leak for the YAW integral (default: same as "
                         "--integral-tau); keep this short when using a long velocity "
                         "integral, since heading error is unsatisfiable at speed")
    ap.add_argument("--no-aero-dr", action="store_true",
                    help="ABLATION: fixed nominal aerodynamics (no 17-coeff/Xg randomization)")
    ap.add_argument("--kp-rate", type=str, default="25,25,15",
                    help="inner-loop rate P gains (xwing default 25,25,15)")
    ap.add_argument("--ki-rate", type=str, default="6,6,3",
                    help="inner-loop rate I gains (xwing default 6,6,3)")
    ap.add_argument("--net", type=str, default="256,256",
                    help="policy/value hidden layer sizes, comma-separated (e.g. 256,256,256)")
    ap.add_argument("--no-subproc", action="store_true")
    ap.add_argument("--device", type=str, default="cpu",
                    help="torch device; CPU is typically faster for this small MLP + CPU sim")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()

    if args.rel_approach > 0.0 and (args.rel_basin != 0.0 or args.cmd_linear):
        ap.error("--rel-approach is the legacy combined alias; do not combine it with "
                 "--rel-basin or --cmd-linear")
    if args.rel_approach < 0.0 or args.rel_basin < 0.0:
        ap.error("reward weights must be non-negative")
    if args.smoke:
        args.timesteps, args.n_envs = 20_000, 2
    os.makedirs(args.out_dir, exist_ok=True)
    use_integral = not args.no_integral
    use_yaw_integral = not args.no_yaw_integral
    use_wind_est = not args.no_wind_est
    config = {"max_speed": args.max_speed, "speed_min": args.speed_min, "wind_max": args.wind_max, "use_integral": use_integral,
               "use_yaw_integral": use_yaw_integral, "use_wind_est": use_wind_est,
               "yaw_width": args.yaw_width, "yaw_weight": args.yaw_weight,
               "yaw_bias": args.yaw_bias, "heading_frame": args.heading_frame,
               "xwing_aero": args.xwing_aero, "tough_init": args.tough_init,
               "wind_curriculum": args.wind_curriculum, "yaw_gate": args.yaw_gate,
               "yaw_gate_floor": args.yaw_gate_floor, "vel_precision": args.vel_precision,
               "trim_init": args.trim_init, "priv_critic": args.priv_critic,
               "att_cmd": args.att_cmd, "katt": args.katt, "ctrl_freq": args.ctrl_freq,
               "att_rel": args.att_rel, "att_rel_k": args.att_rel_k,
               "trim_ff": args.trim_ff, "trim_ff_k": args.trim_ff_k,
               "trim_ff_thrust": args.trim_ff_thrust, "trim_ff_fin": args.trim_ff_fin,
               "trim_ff_true_wind": not args.trim_ff_est_wind,
               "fin_assist": args.fin_assist, "air_obs": args.air_obs,
               "yaw_att_gate": args.yaw_att_gate, "cov_width": args.cov_width,
               "att_tilt_max": args.att_tilt_max, "att_tilt_ext": args.att_tilt_ext, "rel_obs": args.rel_obs,
               "rel_approach": args.rel_approach, "rel_basin": args.rel_basin,
               "cmd_linear": args.cmd_linear, "rel_width": args.rel_width,
               "rel_floor": args.rel_floor,
               "kp_rate": args.kp_rate, "ki_rate": args.ki_rate,
               "aero_dr": not args.no_aero_dr, "integral_tau": args.integral_tau,
               "yaw_integral_tau": args.yaw_integral_tau,
               "ent_coef": args.ent_coef, "gamma": args.gamma,
               "episode_len": args.episode_len}
    with open(os.path.join(args.out_dir, "config.json"), "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, sort_keys=True)
        f.write("\n")

    base_kwargs = dict(episode_len_sec=args.episode_len, max_speed=args.max_speed,
                       speed_min=args.speed_min, wind_max=args.wind_max,
                       use_wind_est=use_wind_est, use_vel_integral=use_integral,
                       use_yaw_integral=use_yaw_integral, yaw_reward_width=args.yaw_width,
                       yaw_weight=args.yaw_weight, yaw_bias_max=args.yaw_bias,
                       velyaw_heading_frame=args.heading_frame, use_xwing_aero=args.xwing_aero,
                       yaw_gate=args.yaw_gate, yaw_gate_floor=args.yaw_gate_floor,
                       vel_precision=args.vel_precision, yaw_att_gate=args.yaw_att_gate,
                       att_tilt_max=args.att_tilt_max, att_tilt_ext=args.att_tilt_ext, rel_obs=args.rel_obs,
                       rel_approach=args.rel_approach, rel_basin=args.rel_basin,
                       cmd_linear=args.cmd_linear, rel_width=args.rel_width,
                       rel_floor=args.rel_floor,
                       cov_width=args.cov_width,
                       kp_rate=tuple(float(x) for x in args.kp_rate.split(",")),
                       ki_rate=tuple(float(x) for x in args.ki_rate.split(",")),
                       aero_dr=not args.no_aero_dr, integral_tau=args.integral_tau,
                       yaw_integral_tau=args.yaw_integral_tau,
                       priv_obs=args.priv_critic, att_cmd=args.att_cmd, katt=args.katt,
                       ctrl_freq=args.ctrl_freq, fin_assist=args.fin_assist,
                       air_obs=args.air_obs, att_rel=args.att_rel, att_rel_k=args.att_rel_k,
                       trim_ff=args.trim_ff, trim_ff_k=args.trim_ff_k,
                       trim_ff_thrust=args.trim_ff_thrust, trim_ff_fin=args.trim_ff_fin,
                       trim_ff_true_wind=not args.trim_ff_est_wind)
    # tough/trim init only shape TRAINING; eval keeps the level start -> comparable metric
    train_kwargs = dict(base_kwargs, randomize_init=True, tough_init_frac=args.tough_init,
                        trim_init_frac=args.trim_init)
    eval_kwargs = dict(base_kwargs, randomize_init=False)
    train_env = norm_env(args.n_envs, args.seed, not args.no_subproc, True, True, train_kwargs,
                         norm_gamma=args.gamma)
    eval_env = norm_env(1, args.seed + 999, not args.no_subproc, False, False, eval_kwargs,
                        norm_gamma=args.gamma)

    pk = dict(net_arch=[int(x) for x in args.net.split(",")])
    policy = "MlpPolicy"
    if args.priv_critic:
        from priv_policy import PrivACPolicy
        policy = PrivACPolicy
        pk["actor_dim"] = int(train_env.observation_space.shape[0]) - 27
    model = PPO(
        policy, train_env,
        n_steps=args.n_steps, batch_size=4096, n_epochs=10,
        gamma=args.gamma, gae_lambda=args.gae_lambda, clip_range=0.2,
        ent_coef=args.ent_coef, learning_rate=3e-4, max_grad_norm=0.5,
        policy_kwargs=pk,
        tensorboard_log=os.path.join(args.out_dir, "tb"),
        seed=args.seed, verbose=1, device=args.device,
    )

    ckpt = CheckpointCallback(save_freq=max(100_000 // args.n_envs, 1),
                              save_path=os.path.join(args.out_dir, "ckpts"),
                              name_prefix="ppo_ratevel", save_vecnormalize=True)
    evalcb = ProgressPlotCallback(
        eval_env, out_dir=args.out_dir, tag="PPO-velyaw",
        best_model_save_path=os.path.join(args.out_dir, "best"),
        log_path=os.path.join(args.out_dir, "eval"),
        eval_freq=max(50_000 // args.n_envs, 1),
        n_eval_episodes=10, deterministic=True, render=False)

    cbs = [ckpt, evalcb]
    if args.wind_curriculum:
        cbs.append(WindCurriculumCallback(w0=8.0, w1=20.0,
                                          start=int(0.375 * args.timesteps),
                                          end=int(0.75 * args.timesteps), verbose=1))
    model.learn(total_timesteps=args.timesteps, callback=cbs, progress_bar=True)

    model.save(os.path.join(args.out_dir, "ppo_ratevel_final"))
    train_env.save(os.path.join(args.out_dir, "vecnormalize.pkl"))
    write_checkpoint_manifest(
        args.out_dir, os.path.join(args.out_dir, "ppo_ratevel_final.zip"),
        os.path.join(args.out_dir, "vecnormalize.pkl"), model.num_timesteps,
        manifest_name="checkpoint_final.json")
    print(f"[DONE] saved PPO model + vecnormalize to {args.out_dir}/")
    train_env.close(); eval_env.close()


if __name__ == "__main__":
    main()
