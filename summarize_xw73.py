"""Synthesize completed xw73 arm artifacts and update trial 73's Markdown results section."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys


ARMS = ("legacy", "linear", "basin", "both")
BANDS = ("hover", "low", "mid", "high", "vhigh", "top")
START = "<!-- AUTO_RESULTS_START -->"
END = "<!-- AUTO_RESULTS_END -->"


def load_arm(name):
    root = Path(f"results_velyaw_xw73_{name}")
    evaluation_path = root / "envelope_best" / "evaluation.json"
    selection_path = root / "envelope_best" / "selection.json"
    recovery_path = Path(f"{root}_recovery.log")
    missing = [str(p) for p in (evaluation_path, selection_path, recovery_path) if not p.exists()]
    if missing:
        raise FileNotFoundError(f"{name} incomplete; missing {missing}")
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    recovery_text = recovery_path.read_text(encoding="utf-8", errors="replace")
    recovered = re.search(r"recovered .*?=\s*([0-9.]+)%", recovery_text)
    recovery_median = re.search(r"median final err:\s*([0-9.]+)", recovery_text)
    return {
        "evaluation": evaluation,
        "selection": selection,
        "recovery_pct": float(recovered.group(1)) if recovered else None,
        "recovery_median": float(recovery_median.group(1)) if recovery_median else None,
    }


def percent_improvement(baseline, value):
    return 100.0 * (baseline - value) / max(abs(baseline), 1e-9)


def verdict(data):
    legacy = data["legacy"]["evaluation"]
    decisions = {}
    promoted = []
    for name in ARMS[1:]:
        current = data[name]["evaluation"]
        vhigh_gain = percent_improvement(
            legacy["bands"]["vhigh"]["median"], current["bands"]["vhigh"]["median"])
        top_gain = percent_improvement(
            legacy["bands"]["top"]["median"], current["bands"]["top"]["median"])
        slow_ratios = {
            b: current["bands"][b]["median"] / max(legacy["bands"][b]["median"], 1e-9)
            for b in ("hover", "low", "mid", "high")
        }
        zero_crash = current["total_crashes"] == 0
        fast_clear = vhigh_gain >= 20.0 and top_gain >= 20.0
        slow_holds = max(slow_ratios.values()) <= 1.30
        state = ("PROMOTE" if zero_crash and fast_clear and slow_holds else
                 "PARTIAL" if zero_crash and vhigh_gain > 0.0 and top_gain > 0.0 else "FAIL")
        decisions[name] = {
            "verdict": state, "vhigh_improvement_pct": vhigh_gain,
            "top_improvement_pct": top_gain,
            "max_below25_regression_ratio": max(slow_ratios.values()),
            "zero_crashes": zero_crash,
        }
        if state == "PROMOTE":
            promoted.append(name)
    winner = None
    if promoted:
        winner = min(promoted, key=lambda name: (
            data[name]["evaluation"]["worst_band_median"],
            data[name]["evaluation"]["pooled_median"]))
        overall = f"PROMOTE `{winner}` to three-seed replication"
    elif any(d["verdict"] == "PARTIAL" for d in decisions.values()):
        partials = [name for name, d in decisions.items() if d["verdict"] == "PARTIAL"]
        winner = min(partials, key=lambda name: (
            data[name]["evaluation"]["worst_band_median"],
            data[name]["evaluation"]["pooled_median"]))
        overall = f"PARTIAL `{winner}`; test balanced target-band sampling"
    else:
        overall = "FAIL: no reward repair passes the fast-band screen"
    return overall, winner, decisions


def markdown(data, overall, winner, decisions):
    lines = [START, "", f"**Automated screening verdict: {overall}.**", "",
             "Balanced held-out evaluation: 100 episodes per band, selected by the independent "
             "checkpoint-selection seed set.", "",
             "| arm | selected checkpoint | hover | low | mid | high | vhigh | top | worst | crashes | recovery |",
             "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name in ARMS:
        arm, ev, sel = data[name], data[name]["evaluation"], data[name]["selection"]
        cells = []
        for band in BANDS:
            b = ev["bands"][band]
            cells.append(f"{b['median']:.2f} / {b['pct_under_1']:.0f}%")
        recovery = ("—" if arm["recovery_pct"] is None else
                    f"{arm['recovery_pct']:.0f}% ({arm['recovery_median']:.1f} m/s med)")
        lines.append(f"| {name} | {sel['selected_label']} @{sel['selected_step']:,} | "
                     + " | ".join(cells)
                     + f" | {ev['worst_band_median']:.2f} | {ev['total_crashes']} | {recovery} |")
    lines += ["", "Fast-band comparison against legacy:", "",
              "| arm | vhigh improvement | top improvement | worst <25 ratio | gate |",
              "|---|---:|---:|---:|---|"]
    for name, decision in decisions.items():
        lines.append(f"| {name} | {decision['vhigh_improvement_pct']:.1f}% | "
                     f"{decision['top_improvement_pct']:.1f}% | "
                     f"{decision['max_below25_regression_ratio']:.2f}× | "
                     f"**{decision['verdict']}** |")
    lines += ["", "This is a one-seed, 4M-step mechanism screen. Even a PROMOTE verdict is not "
              "final task success; it authorizes three-seed replication and convergence training.",
              "", END]
    return "\n".join(lines)


def main():
    try:
        data = {name: load_arm(name) for name in ARMS}
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2
    overall, winner, decisions = verdict(data)
    summary = {
        "overall": overall, "winner": winner, "decisions": decisions,
        "arms": data,
    }
    Path("xw73_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    doc_path = Path("training_history/73_xw73_reward_ablation.md")
    doc = doc_path.read_text(encoding="utf-8")
    replacement = markdown(data, overall, winner, decisions)
    if START not in doc or END not in doc:
        raise RuntimeError(f"missing auto-result markers in {doc_path}")
    before, rest = doc.split(START, 1)
    _, after = rest.split(END, 1)
    doc_path.write_text(before + replacement + after, encoding="utf-8")
    print(overall)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
