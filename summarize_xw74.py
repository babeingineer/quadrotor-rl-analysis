"""Synthesize the three-seed basin replication and update Trial 74's result block."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys


BANDS = ("hover", "low", "mid", "high", "vhigh", "top")
SEEDS = {
    7300: Path("results_velyaw_xw73_basin"),
    7401: Path("results_velyaw_xw74_basin_s7401"),
    7402: Path("results_velyaw_xw74_basin_s7402"),
}
LEGACY = Path("results_velyaw_xw73_legacy")
START = "<!-- AUTO_RESULTS_START -->"
END = "<!-- AUTO_RESULTS_END -->"


def load_run(seed, root):
    paths = {
        "evaluation": root / "envelope_best" / "evaluation.json",
        "selection": root / "envelope_best" / "selection.json",
        "recovery": Path(f"{root}_recovery.log"),
    }
    missing = [str(path) for path in paths.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"seed {seed} incomplete; missing {missing}")
    evaluation = json.loads(paths["evaluation"].read_text(encoding="utf-8"))
    selection = json.loads(paths["selection"].read_text(encoding="utf-8"))
    recovery_text = paths["recovery"].read_text(encoding="utf-8", errors="replace")
    recovered = re.search(r"recovered .*?=\s*([0-9.]+)%", recovery_text)
    recovery_median = re.search(r"median final err:\s*([0-9.]+)", recovery_text)
    return {
        "evaluation": evaluation,
        "selection": selection,
        "recovery_pct": float(recovered.group(1)) if recovered else None,
        "recovery_median": float(recovery_median.group(1)) if recovery_median else None,
    }


def decision(legacy, current):
    def improvement(band):
        base = legacy["bands"][band]["median"]
        value = current["bands"][band]["median"]
        return 100.0 * (base - value) / max(abs(base), 1e-9)

    ratios = {
        band: current["bands"][band]["median"]
        / max(legacy["bands"][band]["median"], 1e-9)
        for band in ("hover", "low", "mid", "high")
    }
    passed = (
        current["total_crashes"] == 0
        and improvement("vhigh") >= 20.0
        and improvement("top") >= 20.0
        and max(ratios.values()) <= 1.30
    )
    return {
        "passed": passed,
        "vhigh_improvement_pct": improvement("vhigh"),
        "top_improvement_pct": improvement("top"),
        "max_below25_regression_ratio": max(ratios.values()),
        "zero_crashes": current["total_crashes"] == 0,
    }


def render(runs, decisions, replicated):
    verdict = (
        "REPLICATED: basin passes all three training seeds"
        if replicated else
        "NOT REPLICATED: at least one basin seed misses the relative gate"
    )
    lines = [
        START, "", f"**Automated replication verdict: {verdict}.**", "",
        "Balanced held-out evaluation uses 100 episodes per band on the same episode seeds.", "",
        "| train seed | selected checkpoint | hover | low | mid | high | vhigh | top | worst | pooled | crashes | recovery | gate |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for seed in SEEDS:
        run = runs[seed]
        ev, sel, dec = run["evaluation"], run["selection"], decisions[seed]
        cells = [f"{ev['bands'][band]['median']:.2f}" for band in BANDS]
        recovery = f"{run['recovery_pct']:.0f}% ({run['recovery_median']:.1f} med)"
        gate = "PASS" if dec["passed"] else "FAIL"
        lines.append(
            f"| {seed} | {sel['selected_label']} @{sel['selected_step']:,} | "
            + " | ".join(cells)
            + f" | {ev['worst_band_median']:.2f} | {ev['pooled_median']:.2f} | "
              f"{ev['total_crashes']} | {recovery} | **{gate}** |"
        )
    lines += [
        "", "Relative gate details against the Trial 73 legacy baseline:", "",
        "| seed | vhigh improvement | top improvement | worst <25 ratio |",
        "|---:|---:|---:|---:|",
    ]
    for seed in SEEDS:
        dec = decisions[seed]
        lines.append(
            f"| {seed} | {dec['vhigh_improvement_pct']:.1f}% | "
            f"{dec['top_improvement_pct']:.1f}% | "
            f"{dec['max_below25_regression_ratio']:.2f}x |"
        )
    lines += [
        "", "Replication does not imply operational acceptance. The controller must still reach "
        "<1 m/s median and >=85% below 1 m/s in every band, zero crashes, acceptable hover/low "
        "yaw, and robust upset recovery.", "", END,
    ]
    return "\n".join(lines), verdict


def main():
    try:
        legacy_path = LEGACY / "envelope_best" / "evaluation.json"
        if not legacy_path.exists():
            raise FileNotFoundError(f"missing legacy baseline: {legacy_path}")
        legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
        runs = {seed: load_run(seed, root) for seed, root in SEEDS.items()}
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2

    decisions = {
        seed: decision(legacy, run["evaluation"])
        for seed, run in runs.items()
    }
    replicated = all(item["passed"] for item in decisions.values())
    replacement, verdict = render(runs, decisions, replicated)
    summary = {
        "verdict": verdict,
        "replicated": replicated,
        "decisions": decisions,
        "runs": runs,
    }
    Path("xw74_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    doc_path = Path("training_history/74_xw74_basin_replication.md")
    doc = doc_path.read_text(encoding="utf-8")
    if START not in doc or END not in doc:
        raise RuntimeError(f"missing auto-result markers in {doc_path}")
    before, rest = doc.split(START, 1)
    _, after = rest.split(END, 1)
    doc_path.write_text(before + replacement + after, encoding="utf-8")
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
