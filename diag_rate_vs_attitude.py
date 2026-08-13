"""Why does the RATE interface (CTBR) work at low speed and fail at speed?

Empirical starting point, from the campaign's own configs:
  xw48c  0-10 m/s   att_cmd=False (RATE)      -> 0.44 median, 0.27 at hover  (best low-speed)
  xw17   0-25 m/s   att_cmd=False (RATE)      -> 5.26 plateau
  xw35b  10-18      att_cmd=True  (ATTITUDE)  -> 0.77
  xw55a  25-34      att_cmd=True  (ATTITUDE)  -> 5.73
So rate control is not inferior in general — it owns the low band. The question is what breaks
above ~10 m/s.

This isolates the interface from the policy entirely. Put the aircraft AT trim for a commanded
level flight at speed V, then issue the perfect "hold" command for each interface and measure how
far the attitude drifts with NO policy in the loop:

  RATE     : omega_des = 0   (hold current attitude by commanding zero body rate)
  ATTITUDE : bz_des = trim thrust axis (hold this specific attitude)

Both get identical trim thrust and elevon commands. Any difference is purely the interface.

    python diag_rate_vs_attitude.py
"""
import numpy as np
from scipy.spatial.transform import Rotation

from rate_vel_aviary import RateVelAviary

SPEEDS = [2.0, 6.0, 10.0, 14.0, 18.0, 25.0, 34.0, 45.0]
HOLD_SEC = 2.0


def trim_for(V):
    """Level-flight trim (attitude, elevon, thrust) at speed V from the offline table."""
    z = np.load("trim_table.npz")
    sp, ga, rv, des, th = z["speeds"], z["gammas"], z["rotvecs"], z["des"], z["thrusts"]
    j = int(np.argmin(np.abs(ga)))                       # gamma = 0
    i = int(np.argmin(np.abs(sp - V)))
    R = Rotation.from_rotvec(rv[i, j]).as_matrix()
    return R, float(des[i, j]), float(th[i, j])


def thrust_action(env, T):
    if T >= env.NOMINAL_HOVER:
        return (T - env.NOMINAL_HOVER) / (env.MAX_TOTAL_THRUST - env.NOMINAL_HOVER)
    return T / env.NOMINAL_HOVER - 1.0


def run(att_cmd, V, seed=0):
    env = RateVelAviary(use_xwing_aero=True, speed_min=V, max_speed=V, wind_max=0.0,
                        randomize_init=True, trim_init_frac=1.0, aero_dr=False,
                        att_cmd=att_cmd, katt=1.5, episode_len_sec=HOLD_SEC + 1.0,
                        kp_rate=(25, 25, 15), ki_rate=(6, 6, 3))
    env.reset(seed=seed)
    R_t, de_t, T_t = trim_for(V)
    # place the aircraft exactly at the table trim, flying level at V
    env.target_vel = np.array([V, 0.0, 0.0])
    aT = float(np.clip(thrust_action(env, T_t), -1, 1))
    fin = float(np.clip(de_t / env.FIN_MAX, -1, 1))
    if att_cmd:
        xy = R_t[:2, 2]                                   # world-frame trim thrust axis
        n = float(np.linalg.norm(xy))
        if n > 0.985:
            xy = xy * (0.985 / n)
        act = np.array([fin, fin, aT, xy[0], xy[1], 0.0], dtype=np.float32)
    else:
        act = np.array([fin, fin, aT, 0.0, 0.0, 0.0], dtype=np.float32)   # omega_des = 0
    tilt0 = np.degrees(np.arccos(np.clip(
        np.array(__import__("pybullet").getMatrixFromQuaternion(env.quat[0])).reshape(3, 3)[2, 2],
        -1, 1)))
    N = int(HOLD_SEC / env.CTRL_TIMESTEP)
    drift = []
    for _ in range(N):
        env.step(act)
        import pybullet as pb
        R = np.array(pb.getMatrixFromQuaternion(env.quat[0])).reshape(3, 3)
        drift.append(np.degrees(np.arccos(np.clip(R[2, 2], -1, 1))) - tilt0)
    env.close()
    return float(np.abs(drift[-1])), float(np.max(np.abs(drift)))


def main():
    print("Holding TRIM with a perfect command, no policy, no wind, no DR.")
    print(f"Attitude drift after {HOLD_SEC:g} s — how hard the INTERFACE makes it to just hold on.\n")
    print(f"{'V':>5}{'RATE drift':>13}{'ATT drift':>12}{'ratio':>9}")
    print("-" * 40)
    for V in SPEEDS:
        try:
            r_end, _ = run(False, V)
            a_end, _ = run(True, V)
            ratio = r_end / max(a_end, 1e-6)
            print(f"{V:>5.0f}{r_end:>12.1f}°{a_end:>11.1f}°{ratio:>8.1f}x")
        except Exception as exc:
            print(f"{V:>5.0f}  failed: {exc}")
    print("\nRATE holds attitude only through the rate loop's ability to keep omega at exactly 0;")
    print("any residual rate INTEGRATES into attitude error. ATTITUDE commands the angle itself,")
    print("so a steady disturbance produces a bounded offset instead of unbounded drift.")


if __name__ == "__main__":
    main()
