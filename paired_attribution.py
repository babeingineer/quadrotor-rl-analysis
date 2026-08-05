"""Attribute the switch's precision effect on the SAME episodes, both ways.

The fired-vs-unfired split cannot answer "what did arming cost?", because the detector fires
precisely on episodes that were already going wrong. The harness is deterministic, so joining
armed and disarmed runs on (band, seed) gives a true paired test: for each episode where the
switch engaged, what was the error with it and without it?

    python eval_composite.py --episodes 400 --upsets 1 --dump paired_disarmed.npz
    python eval_composite.py --episodes 400 --upsets 1 --recovery --dump paired_armed.npz
    python paired_attribution.py
"""
import numpy as np

a = dict(np.load("paired_armed.npz", allow_pickle=True))
d = dict(np.load("paired_disarmed.npz", allow_pickle=True))

key_a = {(b, s): i for i, (b, s) in enumerate(zip(a["band"], a["seed"]))}
key_d = {(b, s): i for i, (b, s) in enumerate(zip(d["band"], d["seed"]))}
common = sorted(set(key_a) & set(key_d))
print(f"joined {len(common)} episodes present in both arms "
      f"(armed {len(a['band'])}, disarmed {len(d['band'])})")

ea = np.array([a["vel_err"][key_a[k]] for k in common])
ed = np.array([d["vel_err"][key_d[k]] for k in common])
fired = np.array([bool(a["fired"][key_a[k]]) for k in common])
bands = np.array([k[0] for k in common])

# Determinism check: unfired episodes must be byte-identical between arms, since the same net
# flew them. If they are not, the comparison is contaminated and nothing below is valid.
drift = np.abs(ea[~fired] - ed[~fired])
print(f"\ndeterminism control: {(~fired).sum()} unfired episodes, "
      f"max |armed - disarmed| = {drift.max():.2e}  "
      f"({'OK — identical' if drift.max() < 1e-9 else 'FAIL — arms not comparable'})")

print(f"\n=== the {fired.sum()} episodes where the switch ENGAGED (paired) ===")
print(f"{'':<18}{'mean':>8}{'median':>8}{'p90':>8}{'max':>8}")
for tag, e in (("with switch", ea[fired]), ("without switch", ed[fired])):
    if len(e):
        print(f"{tag:<18}{e.mean():>8.2f}{np.median(e):>8.2f}"
              f"{np.percentile(e, 90):>8.2f}{e.max():>8.2f}")
if fired.sum():
    delta = ea[fired] - ed[fired]
    better = (delta < -0.1).sum()
    worse = (delta > 0.1).sum()
    print(f"\nper-episode: switch HELPED {better}, HURT {worse}, "
          f"neutral {fired.sum() - better - worse}")
    print(f"mean change {delta.mean():+.2f} m/s   median change {np.median(delta):+.2f} m/s")
    print(f"worst regression {delta.max():+.2f}   best improvement {delta.min():+.2f}")
    for b in sorted(set(bands[fired])):
        m = fired & (bands == b)
        print(f"  {b:<13} n={m.sum():>3}  {ed[m].mean():>6.2f} -> {ea[m].mean():>6.2f} "
              f"(mean)   helped {(ea[m] - ed[m] < -0.1).sum()}/{m.sum()}")

print("\n=== pooled over ALL joined episodes ===")
for tag, e in (("armed", ea), ("disarmed", ed)):
    print(f"{tag:<18}{e.mean():>8.2f}{np.median(e):>8.2f}{np.percentile(e, 90):>8.2f}")
