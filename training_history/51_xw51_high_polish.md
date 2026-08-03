# Trial 51 — xw51: high-band polish ladder (coverage→polish phase)

## Why
Staircase v2 covers the envelope; per-band precision needs dedicated polish (xw49b showed
trailing bands hold but don't mature). From xw45b (18–25: 2.39 med, 21%<1), the proven
polish stack: dedicated range + oversample 0.5 + robust-gated +8M stages.
Target: median <1 (the low/mid precedent: 0.88→0.46, 2.35→0.82 via this exact stack).
Fallback on stall >1: teacher–student from the classical cascade (user-briefed).
