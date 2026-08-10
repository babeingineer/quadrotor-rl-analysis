"""Supervisory recovery switch — shared machinery.

A band champion flies precisely but recovers from upsets only 10-22% of the time; the
full-envelope generalist (xw17) recovers 57%, because an upset throws the aircraft into
states inside its training distribution and far outside a specialist's. This module routes
control to the generalist while the aircraft is upset and hands back once it is settled.

Both are RL policies, so this is a routing rule over networks, not a classical controller.

Two things the first implementation got wrong, fixed here:

1. TARGET-SAMPLING LEAK. `apply_cfg` mutates `env.MAX_SPEED` because each policy needs its
   own obs scaling — but the env also samples `target_vel` from `uniform(SPEED_MIN, MAX_SPEED)`
   at reset (rate_vel_aviary.py:592). Applying a policy's cfg mid-episode therefore changed
   what the NEXT episode commanded. `reset_episode()` always restores the band's own range
   before resetting, so the commanded distribution is fixed by the band, not by whichever
   policy happened to be active when the previous episode ended.
2. IMPLICIT START. The episode used to always begin in the recovery policy, which is right
   for an upset test and wrong for a precision test. `start_in_recovery` is now explicit.

DWELL is the ingredient that makes the switch usable: an upset persists, an aggressive
approach manoeuvre does not. Requiring the condition to hold continuously before handover
(and a minimum stay afterwards) is what took spurious firing from 71-83% down to ~18%.
"""
import json

import numpy as np
import pybullet as p_bullet
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from eval_velyaw import env_kwargs
from rate_vel_aviary import RateVelAviary

GENERALIST = "results_velyaw_xw17"      # full-envelope 0-25: 57% recovery + 23% partial


def load_policy(d):
    """Model + its VecNormalize stats. Normalisation is applied by hand (rather than through
    a VecNormalize wrapper) because two policies share one env and each needs its own stats."""
    cfg = json.load(open(f"{d}/config.json"))
    model = PPO.load(f"{d}/best/best_model.zip", device="cpu")
    stats = VecNormalize.load(f"{d}/vecnormalize.pkl",
                              DummyVecEnv([lambda: RateVelAviary(use_xwing_aero=True)]))
    return {"dir": d, "cfg": cfg, "model": model,
            "mean": stats.obs_rms.mean, "var": stats.obs_rms.var,
            "clip": stats.clip_obs, "eps": stats.epsilon,
            "obs_dim": int(np.asarray(stats.obs_rms.mean).size)}


def check_compatible(nom, rec):
    """Both policies must read the same obs vector, or the switch is silently feeding one of
    them garbage. Obs-dimension flags (wind est, integrals, air_obs, priv, att_rel) differ
    between generations of this project, so fail loudly instead of broadcasting by accident."""
    if nom["obs_dim"] != rec["obs_dim"]:
        raise ValueError(f"obs dim mismatch: {nom['dir']} has {nom['obs_dim']}, "
                         f"{rec['dir']} has {rec['obs_dim']} — cannot share one env")


def apply_cfg(env, p):
    """Point the env at this policy's action interface + obs scaling before using it."""
    c = p["cfg"]
    env.MAX_SPEED = float(c.get("max_speed", 25.0))
    env.ATT_CMD = bool(c.get("att_cmd", False))
    env.KATT = float(c.get("katt", 1.5))
    env.FIN_ASSIST = float(c.get("fin_assist") or 0.0)
    env.INTEGRAL_TAU = float(c.get("integral_tau", 3.0))
    yt = c.get("yaw_integral_tau")
    env.YAW_INTEGRAL_TAU = float(env.INTEGRAL_TAU if yt is None else yt)


def reset_episode(env, seed, lo, hi):
    """Reset with the BAND's commanded-speed range, never a policy's leftover scaling."""
    env.SPEED_MIN, env.MAX_SPEED = float(lo), float(hi)
    return env.reset(seed=seed)


# Calibrated on recorded nominal + upset trajectories across all four bands (calib_upset.py):
# nominal false-fire 3% (worst band 7%) at 87% upset detection. The earlier hand-set values
# (absolute tilt 84 deg, rate 2.5, sink 15, arm 0.4 s) fired on 47% of nominal flights.
TILT_MARGIN = 60.0      # deg of tilt ABOVE the trim attitude for the commanded velocity
SINK_THR = 25.0         # m/s of sink beyond the commanded vertical rate
RATE_THR = 6.0          # rad/s body-rate norm; these policies use >2.5 rad/s routinely
ARM_SEC = 0.8           # sustained seconds before handover
STAY_SEC = 1.0          # minimum seconds engaged
SETTLE_MARGIN = 45.0    # deg over trim tilt still considered "recovered enough to hand back"
# HYSTERESIS, deliberately asymmetric: handover triggers at rate > RATE_THR (6.0) but handback
# demands rate < 1.5 and tilt within SETTLE_MARGIN (< TILT_MARGIN). The gap between the two is
# not dead space to be tuned away — it is what stops the switch oscillating around a single
# threshold, and STAY_SEC reinforces it in time the way these bounds do in state.

_TRIM = None


def _trim_ref():
    """Trim tilt (deg) vs (speed, climb angle) — a tailsitter's normal attitude is a strong
    function of speed, so the detector must compare tilt against trim, not against a constant."""
    global _TRIM
    if _TRIM is None:
        from scipy.spatial.transform import Rotation
        z = np.load("trim_table.npz")
        sp, ga, rv = z["speeds"], z["gammas"], z["rotvecs"]
        t = np.array([[np.degrees(np.arccos(np.clip(
            Rotation.from_rotvec(rv[i, j]).as_matrix()[2, 2], -1.0, 1.0)))
            for j in range(len(ga))] for i in range(len(sp))])
        _TRIM = (sp, ga, t)
    return _TRIM


def expected_tilt(target_vel):
    """Tilt the aircraft SHOULD hold to fly the commanded velocity.

    UNITS BUG FIXED 2026-08-08: `ga` (the trim table's gammas) is in RADIANS, but gamma was
    computed in DEGREES and compared directly. argmin then always landed on an end column —
    the -40 deg trim for ANY descent and the +40 deg trim for ANY climb — so a level 30 m/s
    command reported 93 deg of expected tilt instead of ~54. Both stay in radians now.
    """
    sp, ga, t = _trim_ref()
    speed = float(np.linalg.norm(target_vel))
    gamma = float(np.arcsin(np.clip(target_vel[2] / max(speed, 1e-6), -1.0, 1.0)))   # radians
    j = int(np.argmin(np.abs(ga - gamma)))
    return float(np.interp(speed, sp, t[:, j]))


def _tilt_deg(env):
    R = np.array(p_bullet.getMatrixFromQuaternion(env.quat[0])).reshape(3, 3)
    return np.degrees(np.arccos(np.clip(float(R[2, 2]), -1.0, 1.0)))


def is_upset(env, exp_tilt, tilt_margin=TILT_MARGIN, sink_thr=SINK_THR, rate_thr=RATE_THR):
    """Keyed on STATE, relative to the trim the command implies.

    Not velocity error: a normal episode starts at rest and must accelerate, so its velocity
    error legitimately begins at 10-45 m/s — that trigger detects "approach in progress" and
    fired on 83% of nominal flights. Not absolute tilt either: nominal cruise tilt reaches
    92-110 deg at 18-34 m/s, so a fixed limit calls ordinary fast flight an upset.
    """
    return (_tilt_deg(env) > exp_tilt + tilt_margin
            or float(env.target_vel[2] - env.vel[0][2]) > sink_thr
            or float(np.linalg.norm(env.ang_v[0])) > rate_thr)


def is_settled(env, vel_err, exp_tilt):
    """Hand back once the aircraft is near the attitude its command implies — again relative
    to trim, or the generalist would never hand back during fast cruise (where trim tilt alone
    exceeds any absolute 'settled' limit)."""
    return (_tilt_deg(env) < exp_tilt + SETTLE_MARGIN and vel_err < 8.0
            and float(np.linalg.norm(env.ang_v[0])) < 1.5)


def act(env, p):
    raw = env._computeObs().astype(np.float64)
    norm = np.clip((raw - p["mean"]) / np.sqrt(p["var"] + p["eps"]), -p["clip"], p["clip"])
    a, _ = p["model"].predict(norm.astype(np.float32).reshape(1, -1), deterministic=True)
    return a.reshape(-1)


def run_episode(env, nom, rec, seed, lo, hi, ep_len, start_in_recovery,
                arm_sec=ARM_SEC, stay_sec=STAY_SEC, steady_window=3.0):
    """One switched episode. Returns the same fields the plain evals report, plus switch
    telemetry, so precision and recovery can be scored from a single rollout."""
    dt = env.CTRL_TIMESTEP
    N = int(ep_len / dt)
    need_hot, min_dwell = int(arm_sec / dt), int(stay_sec / dt)
    k_steady = N - int(steady_window / dt)

    reset_episode(env, seed, lo, hi)
    tgt_speed = float(np.linalg.norm(env.target_vel))
    wind = float(np.linalg.norm(env.wind))
    exp_tilt = expected_tilt(env.target_vel)        # fixed per episode: the command is constant
    using_rec = bool(start_in_recovery)
    hot, dwell, n_sw, rec_steps, fired = 0, 0, 0, 0, bool(start_in_recovery)
    errs, verrs, yerrs, crashed = [], [], [], False

    for k in range(N):
        p = rec if using_rec else nom
        apply_cfg(env, p)
        _, _, term, trunc, info = env.step(act(env, p))
        err = info["vel_error"]
        errs.append(err)
        if k >= k_steady:
            verrs.append(err)
            yerrs.append(abs(np.degrees(info["yaw_error"])))
        hot = hot + 1 if is_upset(env, exp_tilt) else 0
        if using_rec:
            rec_steps += 1
            dwell += 1
            if dwell >= min_dwell and is_settled(env, err, exp_tilt):
                using_rec, n_sw = False, n_sw + 1
        elif hot >= need_hot:
            using_rec, dwell, n_sw, fired = True, 0, n_sw + 1, True
        if term or trunc:
            crashed = term and k < N - 1
            break

    tail = int(2.0 / dt)
    return {"vel_err": float(np.mean(verrs)) if verrs else float("nan"),
            "yaw_err": float(np.mean(yerrs)) if yerrs else float("nan"),
            "final_err": float(np.mean(errs[-tail:])) if len(errs) > tail else float(errs[-1]),
            "crashed": bool(crashed), "tgt_speed": tgt_speed, "wind": wind,
            "switches": n_sw, "frac_rec": rec_steps / max(len(errs), 1), "fired": fired}


def build_env(cfg, ep_len, lo, hi, upset=False):
    """Env from the band champion's config, restricted to the band's commanded range."""
    kw = env_kwargs(cfg, ep_len, speed_min=lo, max_speed=hi,
                    randomize_init=bool(upset),
                    tough_init_frac=1.0 if upset else 0.0)
    return RateVelAviary(**kw)
