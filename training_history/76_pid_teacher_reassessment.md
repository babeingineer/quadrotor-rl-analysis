# Trial 76 — PID-teacher initialization: reassessed head-to-head (user proposal)

**STATUS: ANALYSIS ONLY (evaluation, no training).**

## The proposal, and why it deserved a fresh test
User, 2026-08-07: *"how about researching on the pid teacher trained rl agent? i think it can
succeed as even though pid is bad, rl is just start from the pid's work to getting better."*
Followed by: *"ofc, the best way is pure rl training? but if it's hard, pid trained rl agent is
also an option."*

This is **not** the mechanism [ELIMINATED.md](ELIMINATED.md) already refuted. That entry is
*distillation as the final answer*, which fails trivially: you cannot distil a worse policy into
a better one. The user's proposal is **initialization** — behaviour-clone the teacher, then let
RL improve past it. That is standard practice, and it attacks the real problem trial 70 exposed
(a reward with no far-field gradient) in the same way trim-init did, but everywhere in the state
space rather than only at the start state. A BC-initialised policy also still *deploys* as a
plain network, so it is compatible with the pure-RL constraint on the same grounds trim-init was
accepted.

The premise "pid is bad" is also wrong as stated, which made the idea look stronger: trial 21's
cascade reaches **mid-band median 0.20 m/s with 60% of episodes < 1**, versus the RL mid
specialist's 0.77. Where it is stable, the classical controller is ~3.8× more precise than RL.

## The question that decides it
Trial 75 found the fast-band deficit is a **descent stabilization** failure. So: does the teacher
possess the skill the student lacks? Measured with the same stratified γ sweep used on the RL
policies (γ forced, equal n per angle, full DR, wind 0–15).

### Apparatus repair first (two false starts, both mine)
1. Ran the sweep with the module's **default** gains (kp=1.2 ki=0.4 katt=4.0 **ff=1.0**) and got
   21–35 m/s error everywhere with the aircraft sinking at −26 m/s. Those defaults are the
   *untuned* ones; `ff=1.0` closes the est-attitude coupling loop the docstring warns about.
2. Confirmed against the stock evaluator, which reproduced the same garbage (mid mean 33.13) —
   proving the fault was configuration, not my harness.

Trial 21's winning config is **kp=0.6 ki=0.15 katt=1.8 ff=0.2** with elevator assist kfin=1.
With it, the stock evaluator returns mean 3.88 / median 1.28 / 45% <1 over 0–25 m/s — sane, and
in family with trial 21. All numbers below use that config.

## Result — the teacher does NOT have the missing skill

| band | direction | RL specialist | classical (tuned) | winner |
|---|---|---|---|---|
| mid 10–18 | descents | **1.83** | 4.15 | RL by 2.3× |
| mid 10–18 | climbs | **0.79** | 3.05 | RL by 3.9× |
| vhigh 25–34 | descents | **10.16** | 16.19 | RL by 1.6× |
| vhigh 25–34 | climbs | **2.44** | 5.83 | RL by 2.4× |

| band | descent/climb asymmetry: RL | classical |
|---|---|---|
| mid | 2.3× | 1.36× |
| vhigh | 4.2× | 2.78× |

The classical controller is **less asymmetric but uniformly worse**. It is not better at
descents; it is evenly mediocre. Its vertical tracking in descents is genuinely good (vert err
+1.5 to +2.4 at mid, where RL at vhigh is +6.1 short), but that does not translate into lower
total error, because it loses more elsewhere in the velocity vector.

**Verdict: BC-initialisation from this teacher would start the policy BELOW where RL already
converges, at every band and both directions tested.** It cannot raise the ceiling. At best it
would shorten early training — and early training is not the bottleneck; the fast-band plateau
is.

## What survives of the idea
- The teacher's **precision on stable draws** (mid median 0.20, 60% <1) is real and unexploited.
  It shows the mid-band residual is not a control-authority limit. But that is a
  precision-on-easy-draws advantage, not the descent competence trial 75 says is missing.
- If a teacher were ever used, the useful target is the ~60% of draws where fixed gains stay
  stable; on the rest the teacher *destabilises* (trial 21: "the mean is destroyed by a minority
  of DR/wind draws"), and cloning it would clone the instability.

## Honest limits
- The γ-stratified protocol puts equal mass on ±40°, whereas uniform-on-the-sphere sampling
  concentrates near γ=0. So these absolute numbers are **harder** than trial 21's and should not
  be compared to it directly. The RL-vs-classical comparison is unaffected: both were measured
  under the identical protocol, same seeds, same env.
- Only mid and vhigh were tested. The teacher may still win at hover/low, where trial 21 showed
  0.65 median — but those bands are already solved (0.27/0.44), so a teacher has no room there.
- Classical gains were not re-tuned per band or per flight-path angle. A descent-specific gain
  schedule might do better; that is a tuning campaign, not an RL result, and nobody has run it.
