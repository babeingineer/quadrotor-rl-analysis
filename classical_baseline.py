"""Classical 'manual-control' baseline for the velyaw task.

Cascade: velocity error (P + TRUE integral) + disturbance-observer feedforward
  -> desired force vector -> thrust magnitude + desired body-z direction
  -> attitude P-loop -> body-rate commands into the existing PID rate loop.
Uses ONLY policy-visible quantities (vel, target, R, omega, wind_est, nominal mass).
Same eval protocol as eval_velyaw (steady-state = final 3 s), full DR + wind 0-15.

    python classical_baseline.py --episodes 60 [--kp 1.2 --ki 0.4 --katt 4.0]
"""
import argparse
import numpy as np
import pybullet as p
from rate_vel_aviary import RateVelAviary


class ClassicalController:
    def __init__(self, env, kp=1.2, ki=0.4, katt=4.0, kyaw=1.5, int_clamp=8.0, ff=1.0, v0=0.0, kfin=0.0):
        self.e = env
        self.kp, self.ki, self.katt, self.kyaw = kp, ki, katt, kyaw
        self.int_clamp = int_clamp
        self.ff = ff   # observer feedforward scale (1=full; <1 damps the est-attitude coupling loop)
        self.kfin = kfin  # elevon assist: elevator follows the pitch-axis command
        #                   (surface authority scales with V^2)
        self.v0 = v0   # gain-scheduling speed (m/s): gains shrink ~1/(1+(V/v0)^2);
        #               0 = fixed gains
        self.iv = np.zeros(3)                       # TRUE (non-leaky) velocity-error integral
        self.m_nom = env.NOMINAL_MASS
        self.g = 9.8

    def reset(self):
        self.iv = np.zeros(3)

    def act(self, dt):
        e = self.e
        R = np.array(p.getMatrixFromQuaternion(e.quat[0])).reshape(3, 3)
        # gain schedule on policy-visible airspeed (pitot = axial air-relative speed)
        if self.v0 > 0.0:
            pitot = abs(float(R[:, 2] @ (e.vel[0] - e.wind)))
            sched = 1.0 / (1.0 + (pitot / self.v0) ** 2)
        else:
            sched = 1.0
        v_err = e.target_vel - e.vel[0]
        self.iv = np.clip(self.iv + v_err * dt, -self.int_clamp, self.int_clamp)
        a_des = (self.kp * sched) * v_err + self.ki * self.iv
        # force balance with observer feedforward: F_thrust = m(a_des) + mg z - F_ext_est
        F_des = self.m_nom * a_des + np.array([0.0, 0.0, self.m_nom * self.g]) - self.ff * e.wind_est
        T = float(np.linalg.norm(F_des))
        T = float(np.clip(T, 0.05 * e.MAX_TOTAL_THRUST, e.MAX_TOTAL_THRUST))
        d = F_des / (np.linalg.norm(F_des) + 1e-9)   # desired thrust direction (world)
        # thrust action (invert _decode_action)
        if T >= e.NOMINAL_HOVER:
            aT = (T - e.NOMINAL_HOVER) / (e.MAX_TOTAL_THRUST - e.NOMINAL_HOVER)
        else:
            aT = T / e.NOMINAL_HOVER - 1.0
        # attitude P: rotate body-z toward d
        bz = R[:, 2]
        axis = np.cross(bz, d)
        n = np.linalg.norm(axis)
        ang = float(np.arccos(np.clip(bz @ d, -1.0, 1.0)))
        omega_w = (self.katt * sched) * (axis / n) * ang if n > 1e-8 else np.zeros(3)
        omega_b = R.T @ omega_w                      # world -> body rate command
        # yaw: track desired_yaw only when hover-ish (R22 high), matching the task semantics
        if R[2, 2] > 0.6:
            dpsi = e._yaw_error(R)
            omega_b[2] = -self.kyaw * dpsi
        pqr = np.clip(omega_b / e.MAX_RATE, -1.0, 1.0)
        # elevons: symmetric deflection (elevator) assists the pitch channel;
        # effectiveness grows with V^2
        fin = float(np.clip(self.kfin * pqr[1], -1.0, 1.0)) if self.kfin > 0.0 else 0.0
        return np.array([fin, fin, float(np.clip(aT, -1, 1)), pqr[0], pqr[1], pqr[2]])


def evaluate(kp, ki, katt, n=60, ff=1.0, v0=0.0, kfin=0.0, int_clamp=8.0, ep_len=10.0, wind_max=15.0, speed_min=0.0, max_speed=25.0,
             verbose=True):
    env = RateVelAviary(use_xwing_aero=True, randomize_init=False, wind_max=wind_max,
                        speed_min=speed_min, max_speed=max_speed, yaw_bias_max=0.3,
                        episode_len_sec=ep_len, kp_rate=(40, 40, 25), ki_rate=(10, 10, 5))
    ctl = ClassicalController(env, kp=kp, ki=ki, katt=katt, ff=ff, v0=v0, kfin=kfin, int_clamp=int_clamp)
    dt = env.CTRL_TIMESTEP
    N = int(ep_len / dt); k0 = N - int(3.0 / dt)
    rows = []
    for i in range(n):
        env.reset(seed=1000 + i)
        ctl.reset()
        tgt_speed = float(np.linalg.norm(env.target_vel))
        errs, yerrs = [], []
        for k in range(N):
            a = ctl.act(dt)
            _, _, term, trunc, info = env.step(a)
            if k >= k0:
                errs.append(info["vel_error"])
                yerrs.append(abs(np.degrees(info["yaw_error"])))
            if term:
                break
        band = ("hover(0-1)" if tgt_speed < 1 else "low(1-10)" if tgt_speed < 10 else
                "mid(10-18)" if tgt_speed < 18 else "high(18-25)")
        rows.append((band, np.mean(errs) if errs else np.nan,
                     np.mean(yerrs) if yerrs else np.nan, tgt_speed))
    env.close()
    if verbose:
        print(f"\nclassical baseline  kp={kp} ki={ki} katt={katt}  (wind 0-{wind_max:g})")
        print(f"{'band':<12}{'n':>4}{'vel err':>10}{'yaw err':>10}")
        for b in ["hover(0-1)", "low(1-10)", "mid(10-18)", "high(18-25)"]:
            rs = [r for r in rows if r[0] == b]
            if rs:
                print(f"{b:<12}{len(rs):>4}{np.mean([r[1] for r in rs]):>10.2f}"
                      f"{np.mean([r[2] for r in rs]):>10.1f}")
        errs = [r[1] for r in rows]
        print(f"{'ALL':<12}{len(rows):>4}{np.mean(errs):>10.2f}  median {np.median(errs):.2f}"
              f"  <1m/s: {np.mean(np.array(errs) < 1) * 100:.0f}%")
    return float(np.mean([r[1] for r in rows]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=60)
    ap.add_argument("--kp", type=float, default=1.2)
    ap.add_argument("--ki", type=float, default=0.4)
    ap.add_argument("--katt", type=float, default=4.0)
    ap.add_argument("--wind-max", type=float, default=15.0)
    args = ap.parse_args()
    evaluate(args.kp, args.ki, args.katt, n=args.episodes, wind_max=args.wind_max)
