"""Which term of is_upset() fires, per band, during NORMAL flight?

The dwell detector was tuned on the mid champion (18% spurious) but fires on 47% of nominal
episodes pooled across the roster. This attributes the firing to individual terms so the fix
targets the wrong term instead of the threshold in general.

    python diag_upset_terms.py
"""
import numpy as np
import pybullet as p_bullet

from eval_composite import ROSTER
from recovery_switch import act, apply_cfg, build_env, load_policy, reset_episode


def main():
    print(f"{'band':<12}{'policy':<10}{'tilt<.10':>10}{'sink>15':>9}{'tumble':>8}"
          f"{'any':>7}{'tilt_deg p50/p95':>19}{'sink p95':>10}")
    print("-" * 76)
    for lo, hi, d in ROSTER:
        nom = load_policy(d)
        env = build_env(nom["cfg"], 8.0, lo, hi, upset=False)
        dt = env.CTRL_TIMESTEP
        N = int(8.0 / dt)
        tilt_hits = sink_hits = tumble_hits = any_hits = steps = 0
        tilts, sinks = [], []
        for i in range(25):
            reset_episode(env, 5000 + i, lo, hi)
            for k in range(N):
                apply_cfg(env, nom)
                _, _, term, trunc, _ = env.step(act(env, nom))
                R = np.array(p_bullet.getMatrixFromQuaternion(env.quat[0])).reshape(3, 3)
                tc = float(R[2, 2])
                sink = float(env.target_vel[2] - env.vel[0][2])
                tum = float(np.linalg.norm(env.ang_v[0]))
                t1, t2, t3 = tc < 0.10, sink > 15.0, tum > 2.5
                tilt_hits += t1; sink_hits += t2; tumble_hits += t3
                any_hits += (t1 or t2 or t3); steps += 1
                tilts.append(np.degrees(np.arccos(np.clip(tc, -1, 1))))
                sinks.append(sink)
                if term or trunc:
                    break
        env.close()
        pc = lambda x: f"{x / max(steps, 1) * 100:>9.0f}%"
        print(f"{f'{lo:g}-{hi:g}':<12}{d.replace('results_velyaw_', ''):<10}"
              f"{pc(tilt_hits)}{pc(sink_hits)[1:]}{pc(tumble_hits)[2:]}{pc(any_hits)[3:]}"
              f"{np.percentile(tilts, 50):>12.0f}/{np.percentile(tilts, 95):<6.0f}"
              f"{np.percentile(sinks, 95):>8.1f}")


if __name__ == "__main__":
    main()
