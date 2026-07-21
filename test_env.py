"""Sanity checks for RateVelAviary (heavy quad + wind + mass DR):
inner-loop rate tracking (sign+convergence), hover thrust, wind effect, Gym API."""
import numpy as np
import pybullet as p
from rate_vel_aviary import RateVelAviary


def body_rate(env):
    R = np.array(p.getMatrixFromQuaternion(env.quat[0])).reshape(3, 3)
    return R.T @ env.ang_v[0]


def test_rate_tracking():
    print("\n=== inner-loop rate tracking with worst-case motor lag (tau=0.25s) ===")
    axes = [("roll(p)", 1, 4.0), ("pitch(q)", 2, 4.0), ("yaw(r)", 3, 2.0)]
    for name, idx, expected in axes:
        for a_val, tag in [(+1.0, "+"), (-1.0, "-")]:
            env = RateVelAviary(gui=False, episode_len_sec=100, mass_range=(10.0, 10.0),
                                wind_max=0.0, motor_tau_range=(0.25, 0.25))  # worst case
            env.reset(seed=0)
            action = np.zeros(4, dtype=np.float32)      # a_T=0 -> nominal hover thrust
            action[idx] = a_val
            hist = []
            for _ in range(150):                         # ~3 s (allow for lag settle)
                env.step(action); hist.append(body_rate(env)[idx - 1])
            rate = hist[-1]
            target = a_val * expected
            # settled near target AND not oscillating (last second std small)
            settled = abs(rate - target) < 0.2 * expected + 0.15
            stable = np.std(hist[-50:]) < 0.1 * expected + 0.05
            ok = "OK" if settled and stable else ("RING" if settled else "FAIL")
            print(f"  {name:9s} cmd {tag}{expected:4.1f} -> {rate:+6.2f} rad/s "
                  f"(last-1s std {np.std(hist[-50:]):.3f})  [{ok}]")
            env.close()


def test_hover():
    print("\n=== hover thrust (a_T=0, mass=10) holds altitude, no wind ===")
    env = RateVelAviary(gui=False, episode_len_sec=100,
                        mass_range=(10.0, 10.0), wind_max=0.0)
    env.reset(seed=1)
    z0 = env.pos[0, 2]
    for _ in range(100):                                  # 2 s
        env.step(np.zeros(4, dtype=np.float32))
    dz, vz = env.pos[0, 2] - z0, env.vel[0, 2]
    print(f"  dz over 2s = {dz:+.3f} m, vz = {vz:+.3f} m/s  "
          f"[{'OK' if abs(dz) < 0.3 and abs(vz) < 0.5 else 'FAIL'}]")
    env.close()


def test_wind():
    print("\n=== wind pushes an uncontrolled-attitude drone downwind ===")
    # hold level attitude + hover thrust; a steady +x wind should drive vx toward +.
    env = RateVelAviary(gui=False, episode_len_sec=100,
                        mass_range=(10.0, 10.0), wind_max=0.0)
    env.reset(seed=2)
    env.wind = np.array([15.0, 0.0, 0.0])                 # force a known wind
    for _ in range(100):                                  # 2 s
        env.step(np.zeros(4, dtype=np.float32))
    vx = env.vel[0, 0]
    print(f"  vx after 2s of +x wind = {vx:+.2f} m/s  [{'OK' if vx > 1.0 else 'FAIL'}]")
    env.close()


def test_saturation():
    print("\n=== motor saturation: total thrust never exceeds 4*40 N ===")
    env = RateVelAviary(gui=False, episode_len_sec=100, mass_range=(11.0, 11.0))
    env.reset(seed=4)
    # command max thrust + max roll rate simultaneously
    _, T, tau = env._control_wrench(1e9, np.array([1e3, 0.0, 0.0]))
    print(f"  achieved T={T:.1f} N (cap {4*env.MOTOR_MAX:.0f}), tau_x={tau[0]:.2f} N·m  "
          f"[{'OK' if T <= 4*env.MOTOR_MAX + 1e-6 else 'FAIL'}]")
    env.close()


def test_wind_observer():
    print("\n=== disturbance observer recovers the true wind force (hover in steady wind) ===")
    env = RateVelAviary(gui=False, episode_len_sec=100, mass_range=(10.0, 10.0),
                        wind_max=0.0, motor_tau_range=(0.10, 0.10))
    env.reset(seed=7)
    env.wind = np.array([12.0, 0.0, 0.0])                 # known steady wind
    for _ in range(120):                                   # let flight + EMA settle
        env.step(np.zeros(4, dtype=np.float32))
    v_rel = env.vel[0] - env.wind
    true_f = -env.WIND_DRAG * np.linalg.norm(v_rel) * v_rel   # actual external force
    est = env.wind_est
    err = np.linalg.norm(est - true_f)
    print(f"  true wind force {np.round(true_f,1)} N  |  estimate {np.round(est,1)} N  "
          f"|  err {err:.1f} N  [{'OK' if err < 3.0 else 'FAIL'}]")
    env.close()


def test_api():
    print("\n=== Gym API / shapes / DR ranges ===")
    env = RateVelAviary(gui=False)
    obs, info = env.reset(seed=2)
    assert obs.shape == (29,), obs.shape
    masses = []
    ep = 0
    obs, _ = env.reset(seed=3)
    for _ in range(1200):
        obs, r, term, trunc, info = env.step(env.action_space.sample())
        assert np.all(np.isfinite(obs)) and np.isfinite(r)
        if term or trunc:
            masses.append(info["mass"]); ep += 1; env.reset()
    print(f"  obs {obs.shape}, 1200 steps, {ep} episodes, all finite")
    print(f"  sampled masses in [{min(masses):.2f}, {max(masses):.2f}] kg  [OK]")
    env.close()


if __name__ == "__main__":
    test_api()
    test_hover()
    test_wind()
    test_wind_observer()
    test_saturation()
    test_rate_tracking()
    print("\nDone.")
