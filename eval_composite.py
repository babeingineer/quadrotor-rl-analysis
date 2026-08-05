"""Evaluate the composite (band-switched) controller: route each commanded target speed to
the band champion that owns it, then pool the results into one envelope-wide report.

Each champion is evaluated inside an env built from ITS OWN config (action interface,
inner-loop gains, MAX_SPEED obs scaling, integral leak), restricted to the speed range it
owns, so the numbers reflect what the switched system would actually do. Switching
transients are NOT modelled here: targets are constant per episode, so a routing decision
is made once at episode start — the same assumption the per-band evals use.

    python eval_composite.py --episodes 400
    python eval_composite.py --episodes 400 --ep-len 20

With `--recovery`, a full-envelope generalist is armed underneath every band as a supervisory
upset-recovery mode (see recovery_switch.py). `--upsets N` adds the recovery column, measured
from failure-state starts. Armed and disarmed runs share one rollout implementation and one
seed sequence, so the precision cost of arming the switch is a paired comparison.

    python eval_composite.py --episodes 400 --upsets 40 --recovery
"""
import argparse
import json
import os

import numpy as np

from eval_velyaw import evaluate
from recovery_switch import GENERALIST

# (lo, hi, run dir) — ownership by COMMANDED target speed. Overlapping training ranges are
# fine; the router picks by commanded speed, so each band is scored on what it would fly.
ROSTER = [
    (0.0, 10.0, "results_velyaw_xw48c"),   # hover + low: 0.46 median, 76% <1, yaw 4.8 deg
    (10.0, 18.0, "results_velyaw_xw35b"),  # mid: 0.82 median, 62% <1
    (18.0, 25.0, "results_velyaw_xw51b"),  # high: 2.03 median
    (25.0, 34.0, "results_velyaw_xw55a"),  # vhigh: 4.23 band median
]


def band_of(speed):
    if speed < 1:
        return "hover(0-1)"
    if speed < 10:
        return "low(1-10)"
    if speed < 18:
        return "mid(10-18)"
    if speed < 25:
        return "high(18-25)"
    if speed < 35:
        return "vhigh(25-35)"
    return "top(35-45)"


def switched_band(d, lo, hi, n, upsets, ep_len, armed, arm, stay, nom_seed=20000):
    """Precision (+ optional recovery) for one band, with the generalist armed or not.
    Disarmed routes the recovery slot back to the champion itself, so both arms execute the
    identical rollout code on identical seeds — the difference is only which net flies."""
    from recovery_switch import (ARM_SEC, GENERALIST, STAY_SEC, build_env, check_compatible,
                                 load_policy, run_episode)
    arm = ARM_SEC if arm is None else arm
    stay = STAY_SEC if stay is None else stay
    nom = load_policy(d)
    rec = load_policy(GENERALIST) if armed else nom
    if armed:
        check_compatible(nom, rec)
    out = {}
    for upset, count, seed0 in (("nominal", n, nom_seed), ("upset", upsets, 1000)):
        if not count:
            continue
        env = build_env(nom["cfg"], ep_len, lo, hi, upset=(upset == "upset"))
        out[upset] = [run_episode(env, nom, rec, seed0 + i, lo, hi, ep_len,
                                  start_in_recovery=(upset == "upset" and armed),
                                  arm_sec=arm, stay_sec=stay) for i in range(count)]
        env.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=400,
                    help="total episodes, split across roster entries by range width")
    ap.add_argument("--ep-len", type=float, default=8.0)
    ap.add_argument("--roster", type=str, default=None,
                    help="optional JSON list of [lo, hi, dir] to override the default roster")
    ap.add_argument("--recovery", action="store_true",
                    help="arm the generalist as a supervisory upset-recovery mode")
    ap.add_argument("--upsets", type=int, default=0,
                    help="failure-state episodes per band for the recovery column (0 = skip)")
    ap.add_argument("--nominal-seed", type=int, default=20000,
                    help="base seed for nominal episodes; kept clear of calib_upset.py's "
                         "5000-range so thresholds are not selected on the scoring episodes")
    ap.add_argument("--dump", type=str, default=None,
                    help="write per-episode records (band, seed, vel_err, fired) to this .npz "
                         "so armed and disarmed runs can be joined into a paired test")
    ap.add_argument("--arm", type=float, default=None, help="dwell: seconds to engage")
    ap.add_argument("--stay", type=float, default=None, help="dwell: minimum seconds engaged")
    args = ap.parse_args()

    roster = json.loads(args.roster) if args.roster else ROSTER
    total_width = sum(hi - lo for lo, hi, _ in roster)
    rows, recov = [], []
    mode = "RECOVERY ARMED" if args.recovery else "champions alone"
    print(f"composite roster ({len(roster)} policies), {args.ep_len:g}s episodes — {mode}")
    switched = args.recovery or args.upsets
    gen_max = 25.0
    if args.recovery:
        gen_max = float(json.load(open(f"{GENERALIST}/config.json")).get("max_speed", 25.0))
        print(f"  generalist {GENERALIST} trained to {gen_max:g} m/s — armed only where the "
              f"band lies inside that envelope")
    for lo, hi, d in roster:
        if not os.path.isdir(d):
            print(f"  !! missing {d} — skipped")
            continue
        n = max(int(round(args.episodes * (hi - lo) / total_width)), 20)
        # Arming the generalist ABOVE its trained range measurably destroys recovery
        # (25-34 band: 28% disarmed -> 5% armed), because it is being asked to fly a command
        # it never saw. Route upsets to it only where it is in-envelope.
        arm_here = bool(args.recovery and hi <= gen_max + 1e-9)
        if switched:
            res = switched_band(d, lo, hi, n, args.upsets, args.ep_len,
                                arm_here, args.arm, args.stay, nom_seed=args.nominal_seed)
            # On an UNARMED band the detector still evaluates, but "switching" routes to the
            # same net — so a fired flag there means no behavioural change. Report it as not
            # fired, or the firing rate counts episodes where nothing happened.
            ok = [(band_of(x["tgt_speed"]), x["vel_err"], x["yaw_err"], x["crashed"],
                   x["tgt_speed"], x["wind"], bool(x["fired"]) and arm_here,
                   args.nominal_seed + i)
                  for i, x in enumerate(res["nominal"]) if not x["crashed"]]
            if "upset" in res:
                f = np.array([x["final_err"] for x in res["upset"]])
                recov.append((lo, hi, f))
        else:
            r = evaluate(d, n=n, ep_len=args.ep_len, speed_min=lo, max_speed=hi)
            ok = [x for x in r if not x[3]]
        e = np.array([x[1] for x in ok])
        extra = ""
        if switched and args.recovery:
            extra = (f"  fired {np.mean([x[6] for x in ok]) * 100:3.0f}%" if arm_here
                     else "  UNARMED (out of generalist envelope)")
        if recov and recov[-1][0] == lo:
            extra += f"  recovered {np.mean(recov[-1][2] < 8) * 100:3.0f}%"
        print(f"  {lo:>4.0f}-{hi:<4.0f} {os.path.basename(d):<24} n={len(ok):>3} "
              f"median {np.median(e):5.2f}  <1 {np.mean(e < 1) * 100:3.0f}%  "
              f"mean {e.mean():5.2f}  p90 {np.percentile(e, 90):5.2f}{extra}")
        rows.extend(ok)

    if not rows:
        print("no results")
        return
    print("\n=== COMPOSITE (pooled, uniform over the covered envelope) ===")
    print(f"{'band':<13}{'n':>4}{'mean':>8}{'median':>8}{'%<1':>6}{'p90':>8}{'yaw':>8}")
    print("-" * 55)
    for b in ["hover(0-1)", "low(1-10)", "mid(10-18)", "high(18-25)",
              "vhigh(25-35)", "top(35-45)"]:
        rs = [r for r in rows if band_of(r[4]) == b]
        if not rs:
            continue
        e = np.array([r[1] for r in rs])
        print(f"{b:<13}{len(rs):>4}{e.mean():>8.2f}{np.median(e):>8.2f}"
              f"{np.mean(e < 1) * 100:>5.0f}%{np.percentile(e, 90):>8.2f}"
              f"{np.mean([r[2] for r in rs]):>7.1f}°")
    print("-" * 55)
    e = np.array([r[1] for r in rows])
    boots = [np.median(np.random.default_rng(i).choice(e, len(e))) for i in range(200)]
    print(f"{'ALL':<13}{len(rows):>4}{e.mean():>8.2f}{np.median(e):>8.2f}"
          f"{np.mean(e < 1) * 100:>5.0f}%{np.percentile(e, 90):>8.2f}")
    print(f"robust median {np.median(e):.2f} "
          f"[CI {np.percentile(boots, 2.5):.2f}-{np.percentile(boots, 97.5):.2f}]")
    for lo, hi in ((0, 5), (5, 10), (10, 15)):
        rs = [r for r in rows if len(r) > 5 and lo <= r[5] < hi]
        if rs:
            eb = np.array([r[1] for r in rs])
            print(f"  wind {lo}-{hi}: n={len(rs)} median {np.median(eb):.2f} "
                  f"<1 {np.mean(eb < 1) * 100:.0f}%")
    if recov:
        allf = np.concatenate([f for _, _, f in recov])
        r = (allf < 8).astype(float)
        rb = [np.mean(np.random.default_rng(i).choice(r, len(r))) for i in range(200)]
        print(f"\nRECOVERY from failure-state starts (n={len(allf)} pooled): "
              f"recovered(<8) {np.mean(allf < 8) * 100:.0f}% "
              f"[CI {np.percentile(rb, 2.5) * 100:.0f}-{np.percentile(rb, 97.5) * 100:.0f}]  "
              f"partial(8-15) {np.mean((allf >= 8) & (allf < 15)) * 100:.0f}%  "
              f"median final {np.median(allf):.1f}")
    if args.recovery:
        fired = np.mean([r[6] for r in rows]) * 100
        print(f"switch fired in {fired:.0f}% of nominal episodes — this is where the "
              f"precision cost comes from")
        # The pooled MEDIAN cannot move at a 3-6% firing rate: it is structurally insensitive
        # to what arming changes. p90 can, and the conditional split below is the statistic
        # that actually answers "what does arming cost when it engages?".
        fr = [r for r in rows if r[6]]
        un = [r for r in rows if not r[6]]
        print(f"{'conditional':<13}{'n':>4}{'mean':>8}{'median':>8}{'%<1':>6}{'p90':>8}")
        for tag, rs in (("fired", fr), ("not fired", un)):
            if rs:
                e = np.array([r[1] for r in rs])
                print(f"{tag:<13}{len(rs):>4}{e.mean():>8.2f}{np.median(e):>8.2f}"
                      f"{np.mean(e < 1) * 100:>5.0f}%{np.percentile(e, 90):>8.2f}")
        if fr:
            print(f"  -> the {len(fr)} fired episodes are the entire precision delta; compare "
                  f"p90 against the disarmed run, not the median")
            print("  NOTE: fired episodes are ALREADY the hard ones (the detector fires because "
                  "the aircraft is upset), so this split cannot separate 'switch caused harm' "
                  "from 'switch fired on a failing flight'. Use --dump on both arms and join "
                  "on (band, seed) — the harness is deterministic, so that is a true paired test.")
    if args.dump:
        np.savez(args.dump,
                 band=np.array([r[0] for r in rows]),
                 vel_err=np.array([r[1] for r in rows], dtype=float),
                 tgt_speed=np.array([r[4] for r in rows], dtype=float),
                 fired=np.array([bool(r[6]) if len(r) > 6 else False for r in rows]),
                 seed=np.array([r[7] if len(r) > 7 else -1 for r in rows], dtype=int))
        print(f"per-episode records -> {args.dump}")


if __name__ == "__main__":
    main()
