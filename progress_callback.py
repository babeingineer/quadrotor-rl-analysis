"""Shared EvalCallback that (a) syncs VecNormalize obs stats before each eval,
(b) saves a velocity-tracking image of the current policy, and (c) refreshes the
training-curve graph. Used by both train.py (PPO) and train_sac.py (SAC) so the two
runs produce directly comparable artifacts."""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from stable_baselines3.common.callbacks import EvalCallback


def unwrap_base(venv):
    """Walk through VecFrameStack/VecNormalize wrappers to the underlying RateVelAviary."""
    while not hasattr(venv, "envs"):
        venv = venv.venv
    return venv.envs[0].unwrapped


class ProgressPlotCallback(EvalCallback):
    def __init__(self, *args, out_dir="results", tag="", **kwargs):
        super().__init__(*args, **kwargs)
        self.out_dir = out_dir
        self.tag = tag
        self.progress_dir = os.path.join(out_dir, "progress")
        os.makedirs(self.progress_dir, exist_ok=True)

    def _on_step(self):
        try:
            self.eval_env.obs_rms = self.model.get_vec_normalize_env().obs_rms
        except Exception:
            pass
        n_before = len(self.evaluations_timesteps) if self.evaluations_timesteps else 0
        out = super()._on_step()
        n_after = len(self.evaluations_timesteps) if self.evaluations_timesteps else 0
        if n_after > n_before:
            step = int(self.num_timesteps)
            for fn in (lambda: self._save_track_plot(step), self._save_curve_plot):
                try:
                    fn()
                except Exception as e:
                    print(f"[warn] plot failed: {e}")
        return out

    def _rollout_episode(self):
        venv = self.eval_env
        base = unwrap_base(venv)
        task = getattr(base, "TASK", "velocity")
        obs = venv.reset()
        target = base.target_pos.copy() if task == "position" else base.target_vel.copy()
        mass, wind, dt = float(base.M), base.wind.copy(), base.CTRL_TIMESTEP
        ts, sig, errs, done, t = [], [], [], False, 0.0
        while not done:
            action, _ = self.model.predict(obs, deterministic=True)
            obs, _, dones, infos = venv.step(action)
            done = bool(dones[0])
            if not done:
                sig.append(infos[0]["pos"] if task == "position" else infos[0]["vel"])
                errs.append(infos[0]["pos_error"] if task == "position" else infos[0]["vel_error"])
                ts.append(t); t += dt
        return np.array(ts), np.array(sig), np.array(errs), target, mass, wind, task

    def _save_track_plot(self, step):
        ts, sig, errs, target, mass, wind, task = self._rollout_episode()
        if len(ts) == 0:
            return
        unit = "m" if task == "position" else "m/s"
        comp = ["x", "y", "z"] if task == "position" else ["vx", "vy", "vz"]
        fig, axs = plt.subplots(4, 1, figsize=(8, 9), sharex=True)
        for i, lab in enumerate(comp):
            axs[i].plot(ts, sig[:, i], color="C0", label=f"{lab} actual")
            axs[i].axhline(target[i], ls="--", color="k", label=f"{lab} target")
            axs[i].set_ylabel(unit); axs[i].grid(alpha=0.3); axs[i].legend(loc="right", fontsize=8)
        axs[3].plot(ts, errs, color="C3"); axs[3].set_ylabel(f"err ({unit})")
        axs[3].set_xlabel("time (s)"); axs[3].grid(alpha=0.3)
        pfx = f"{self.tag} " if self.tag else ""
        fig.suptitle(f"{pfx}step {step:,} | mass={mass:.1f} kg | "
                     f"|wind|={np.linalg.norm(wind):.1f} m/s | "
                     f"steady err={errs[-int(len(errs)/4):].mean():.2f} {unit}")
        fig.tight_layout()
        fig.savefig(os.path.join(self.progress_dir, f"track_{step:08d}.png"), dpi=110)
        fig.savefig(os.path.join(self.progress_dir, "latest_track.png"), dpi=110)
        plt.close(fig)

    def _save_curve_plot(self):
        t = np.array(self.evaluations_timesteps)
        r = np.array(self.evaluations_results).mean(axis=1)
        rs = np.array(self.evaluations_results).std(axis=1)
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.plot(t, r, color="C0", marker="o", ms=3, label="mean eval return")
        ax.fill_between(t, r - rs, r + rs, alpha=0.2, color="C0")
        ax.set_xlabel("timesteps"); ax.set_ylabel("episode return")
        ax.set_title(f"Training progress{' — ' + self.tag if self.tag else ''} "
                     f"(deterministic eval, {self.n_eval_episodes} episodes)")
        ax.grid(alpha=0.3); ax.legend(loc="lower right")
        fig.tight_layout()
        fig.savefig(os.path.join(self.out_dir, "training_curve.png"), dpi=120)
        plt.close(fig)
