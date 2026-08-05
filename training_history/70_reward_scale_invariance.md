# Trial 70 — scale-invariant approach reward (0–50 m/s in ONE policy)

**STATUS: ANALYSIS + IMPLEMENTATION ONLY. NOT TRAINED.** User directive 2026-08-05: *"if
current training finished, just document everything and your research till now in detail and
don't start new training from now on."* The mechanism below is derived from the reward code and
verified numerically; it has **no training result**, and must not be reported as one.

## Why — the question that produced it
User request: *"find a way to train once to make it work for all range 0 to 50m/s"* (note the
target moved 45 → 50 m/s here). Everything in this project so far is a **band specialist**:
four policies routed by commanded speed, because every attempt at one wide-range policy
plateaued ~6× worse than specialists (generalist xw17: 5.26 m/s over 0–25, vs specialists at
0.44 / 0.77). The campaign treated that as a capacity/interference problem and tested capacity
(trial 11, 512×512), LSTM memory (18), privileged critic (30), span/scaffold width (63, 65, 66)
— all refuted. **None of those tests examined the reward's numerical behaviour at speed.**

## The mechanism — the reward is numerically dead far from a fast target
`_computeReward` builds the velocity reward from three terms with **absolute** widths, plus a
linear pull whose coefficient is scaled by the envelope:

```python
s = self.MAX_SPEED / 20.0
d = np.linalg.norm(self.vel[0] - self.target_vel)
W = self.COV_WIDTH if self.COV_WIDTH > 0.0 else 10.0 * s
cov = np.exp(-0.5 * (d / W) ** 2)          # width 5 m/s (COV_WIDTH)
r_vel = (1.0 - np.tanh(d / 2.0)) + cov     # width 2 m/s
r_vel += self.VEL_PRECISION * (1.0 - np.tanh(d / 0.5))   # width 0.5 m/s
...
reward = r_vel + ... - (0.02 / s) * d + smooth            # linear, coeff 0.4/MAX_SPEED
```

An episode starts **at rest**, so a commanded speed V means an initial error d = V. Evaluating
the shaped terms there:

| commanded V | shaped reward at rest | shaped gradient | linear gradient (MAX_SPEED=50) |
|---|---|---|---|
| 5 | 6.2e-01 | 1.3e-01 | 0.0080 |
| 10 | 1.4e-01 | 5.4e-02 | 0.0080 |
| 18 | 1.5e-03 | 1.1e-03 | 0.0080 |
| 25 | 3.7e-06 | 3.7e-06 | 0.0080 |
| 34 | 9.1e-11 | 1.2e-10 | 0.0080 |
| 45 | 2.6e-18 | 4.6e-18 | 0.0080 |
| **50** | **1.9e-22** | **3.9e-22** | 0.0080 |

**All shaped structure vanishes above ~25 m/s** — 21 orders of magnitude across the envelope.
Beyond ~14 m/s of error the shaped gradient drops below the linear one and the reward becomes a
**bare linear ramp with no shape**: no coverage basin, no precision incentive, nothing that
grows as the aircraft closes in.

### Second, independent defect: the linear pull is weakened by asking for more range
The surviving term's coefficient is `0.02/s = 0.4/MAX_SPEED`:

| MAX_SPEED | linear coeff |
|---|---|
| 10 | 0.0400 |
| 18 | 0.0222 |
| 25 | 0.0160 |
| 34 | 0.0118 |
| **50** | **0.0080** |

A 0–50 policy gets **5× weaker** far-field pull than a 0–10 specialist — and it is competing
against control-effort penalties (`smooth` ≈ −2e-3 for |ω| = 2 rad/s) that do **not** shrink.
**Widening the envelope mechanically weakens the only term that still works there.** Banding
was not just cutting the problem up; it was quietly restoring the reward slope.

### What this explains in the existing record
- **trim-init was "the single biggest gain at speed"** (trial 27): it starts episodes *at* the
  target, i.e. inside the tiny region where shaped reward still exists. It was a workaround for
  a dead reward, not a curriculum insight.
- **Fresh fast-band training is a dead end** (trial 54: 5.07 vs 2.03 transfer) — nothing to
  descend from rest.
- **Further training at fast bands always made them worse** (trials 62–66, both span
  directions): with no shaped gradient there, extra steps optimise the smoothness penalty →
  do less → the "loitering equilibrium" first seen at trials 11–12.
- **The generalist plateaued at 5.26** — it spent most of its samples in the flat far field.
- **Precision *weight* changed nothing** (trial 31, 0.7 → 1.5): scaling a term whose value is
  1e-22 leaves it 1e-22. The trial was well run and its null result is now explained.

## Exact code changes (NEW — implemented, not trained)

`rate_vel_aviary.py` — constructor (NEW params):
```python
                 rel_approach: float = 0.0,        # >0: scale-invariant approach basin weight
                 rel_width: float = 0.5,           # basin width as a fraction of commanded speed
                 rel_floor: float = 8.0,           # m/s commanded-speed floor (hover/low)
```
```python
        self.REL_APPROACH = float(rel_approach)
        self.REL_WIDTH = float(rel_width)
        self.REL_FLOOR = float(rel_floor)
```

`rate_vel_aviary.py` — `_computeReward`, after the absolute precision peak (NEW):
```python
        if self.REL_APPROACH > 0.0:
            # SCALE-INVARIANT APPROACH BASIN ... the goal is <1 m/s at any speed, so a relative
            # goal would reward +-25 m/s at 50. But absolute widths are numerically DEAD far
            # from a fast target ... This basin's width is a FRACTION OF THE COMMANDED SPEED,
            # so the pull from rest is the same at 5 and 50 m/s, while the goal stays absolute.
            vs = max(float(np.linalg.norm(self.target_vel)), self.REL_FLOOR)
            r_vel += self.REL_APPROACH * np.exp(-0.5 * (d / (self.REL_WIDTH * vs)) ** 2)
```

`rate_vel_aviary.py` — the linear pull, keyed to commanded speed instead of MAX_SPEED (CHANGED):
```python
        if self.REL_APPROACH > 0.0:
            lin = 0.4 / max(float(np.linalg.norm(self.target_vel)), self.REL_FLOOR)
        else:
            lin = 0.02 / s
        reward = r_vel + self.YAW_WEIGHT * gate * r_yaw + 0.5 * joint - lin * d + smooth
```
`0.4 / V` is not arbitrary: the legacy penalty at full-scale error is `(0.02/s)·MAX_SPEED = 0.4`
exactly, so this reproduces at **every commanded speed** what a specialist tuned to that speed
already felt. Legacy behaviour is bit-identical when `rel_approach = 0` (the default).

`train.py` — flags `--rel-approach` / `--rel-width` / `--rel-floor`, written into `config.json`
and forwarded to `base_kwargs`. `continue_train.py` and `eval_velyaw.env_kwargs` read the three
keys from config with legacy-safe defaults, so old runs load unchanged.

## Design rationale: relative approach, ABSOLUTE goal
The tempting fix — make the whole reward relative (error / commanded speed) — is **wrong for
this task**: at 50 m/s it would pay full reward for ±25 m/s. The goal is absolute (<1 m/s at any
speed), so:
- **approach** terms (linear pull, new basin) → scale-invariant, width ∝ commanded speed;
- **goal** terms (`tanh(d/2)`, `cov` at 5 m/s, precision peak at 0.5 m/s) → untouched, absolute.

Verified numerically (`rel_approach=1.0, rel_width=0.5, rel_floor=8`):

| commanded V | legacy gradient at rest | scale-invariant | ratio |
|---|---|---|---|
| 5 | 1.43e-01 | 3.28e-01 | 2.3× |
| 18 | 9.10e-03 | 5.34e-02 | 5.9× |
| 25 | 8.00e-03 | 3.77e-02 | 4.7× |
| 50 | 8.00e-03 | 1.88e-02 | 2.4× |

Near-field values at V=50 are unchanged in shape (d=1.0: 1.535 → 2.534, the +1.0 basin offset),
so the absolute goal is intact.

### The yaw gate is deliberately untouched
`gate = gf + (1 - gf) * cov` (line ~871) reads the **absolute** coverage Gaussian (W = 5 m/s).
The new basin is a separate additive term in `r_vel` and does **not** feed the gate, so the yaw
specification — yaw commanded and scored at hover/low, released in wing-borne flight via the
`clip(R22,0,1)` attitude gate — behaves exactly as before under `rel_approach`. This matters:
had the basin replaced `cov`, the gate would have started paying yaw at speed, silently
violating the spec. `joint` (line ~868) also stays absolute for the same reason, and `s` still
sets `W` when `COV_WIDTH == 0`.

### Verified: the legacy path is bit-identical
Claim checked, not assumed. A copy of the module with the two additions mechanically removed was
stepped alongside the edited one over **320 steps across 8 seeds with random actions** at
`rel_approach = 0`, same seeds and same action sequence:
`max |new − legacy| = 0.000e+00`. Every existing run and config is therefore unaffected.
(The earlier smoke test compared `rel_approach` 0 vs 1.0 on *different* target draws, which
showed only that both paths execute — it was not evidence of legacy equivalence.)

## Honest limits of this entry
- **No training was run**, so there is no evidence this closes the gap — only that the
  mechanism it targets is real and quantified.
- **The far field was never signal-*free***, as I first wrote. It is a weak, shapeless linear
  ramp (0.008/(m/s) at MAX_SPEED=50) that a value function can in principle follow. The claim
  that survives is "weak and degrading with envelope width", not "absent". Corrected before
  publishing.
- `rel_floor=8` is a guess, not calibrated. It sets hover's effective width (0.5·8 = 4 m/s).
- The basin adds a constant +REL_APPROACH offset near the target, which shifts the return scale;
  VecNormalize handles scale, but it also slightly dilutes the *relative* size of the precision
  peak. If a run ever happens, the ablation should include `rel_approach` 0.5 vs 1.0.
- One variable per trial (lesson from trials 22/23): `rel_approach` bundles the basin AND the
  linear re-keying. They are separable and should be split if a run is ever authorised.

## If training were ever authorised, the pre-registration would be
Baseline = the composite (pooled median 1.22, and per-band 0.44 / 0.77 / 1.77 / 5.73).
Single policy, `--speed-min 0 --max-speed 50 --rel-approach 1.0`, everything else at the
standing recipe (att_cmd, yaw gates, precision 0.7, cov 5, wind 15, trim-init 0.2).
- **SUCCESS**: per-band medians within ~30% of the specialists AND 34–50 m/s covered at all
  (no specialist covers it today) → single-policy path is open.
- **PARTIAL**: fast bands improve but slow bands regress → interference is real *on top of* the
  reward defect; next step would be capacity or conditioning, now on a fair reward.
- **FAILURE**: no change → the reward was not the binding constraint, and the banded composite
  stands as the deliverable.
