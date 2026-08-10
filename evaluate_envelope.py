"""Balanced, per-band physical evaluation of one explicit 0–45 m/s checkpoint pair."""
import argparse
import json
from pathlib import Path

from select_envelope_checkpoint import evaluate_candidate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--model-file", default=None)
    ap.add_argument("--vecnormalize-file", default=None)
    ap.add_argument("--episodes-per-band", type=int, default=100)
    ap.add_argument("--ep-len", type=float, default=8.0)
    ap.add_argument("--steady-window", type=float, default=3.0)
    ap.add_argument("--seed-base", type=int, default=27300)
    ap.add_argument("--output", default=None)
    args = ap.parse_args()
    bundle = Path(args.dir) / "envelope_best"
    model = args.model_file or str(bundle / "best_model.zip")
    norm = args.vecnormalize_file or str(bundle / "vecnormalize.pkl")
    result = evaluate_candidate(
        args.dir, {"label": "envelope-best", "step": -1, "model": model,
                   "vecnormalize": norm},
        args.episodes_per_band, args.ep_len, args.steady_window, args.seed_base)
    print(f"{'band':<8}{'n':>5}{'mean':>9}{'median':>9}{'%<1':>8}{'p90':>9}"
          f"{'crash':>8}")
    print("-" * 56)
    for name, values in result["bands"].items():
        print(f"{name:<8}{values['n']:>5}{values['mean']:>9.2f}{values['median']:>9.2f}"
              f"{values['pct_under_1']:>7.1f}%{values['p90']:>9.2f}"
              f"{values['crashes']:>8}")
    print("-" * 56)
    print(f"worst median {result['worst_band_median']:.2f} | pooled median "
          f"{result['pooled_median']:.2f} | pooled <1 {result['pooled_pct_under_1']:.1f}% | "
          f"crashes {result['total_crashes']}")
    output = Path(args.output) if args.output else bundle / "evaluation.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
