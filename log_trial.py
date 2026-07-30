"""Append the automated results section to a trial's training_history MD file.
Chained after training + analysis:  train.py && analyze_velyaw.py && log_trial.py

    python log_trial.py --dir results_velyaw_xw8b --md training_history/05_xw8b_continuation.md

Collects: final step count, eval-curve stats (evaluations.npz), the training curve image
(copied into training_history/figs/), and the key sections of the analysis log (physical
eval table, dive-recovery test, traces). Idempotent-ish: appends a timestamped section.
"""
import argparse, json, os, shutil, re
from datetime import datetime
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="results dir of the finished run")
    ap.add_argument("--md", required=True, help="training_history/<trial>.md to append to")
    ap.add_argument("--analysis", default=None,
                    help="analysis log (default <dir>_analysis.log)")
    args = ap.parse_args()
    D = args.dir.rstrip("/\\")
    analysis = args.analysis or f"{D}_analysis.log"

    lines = [f"\n---\n\n## AUTO-CAPTURED RESULTS ({datetime.now():%Y-%m-%d %H:%M})\n"]

    # config
    try:
        cfg = json.load(open(os.path.join(D, "config.json")))
        lines.append(f"**config**: `{json.dumps(cfg)}`\n")
    except Exception as e:
        lines.append(f"(config.json unreadable: {e})\n")

    # eval curve stats
    try:
        z = np.load(os.path.join(D, "eval", "evaluations.npz"))
        r = z["results"].mean(axis=1); t = z["timesteps"]
        lines.append(f"**eval curve**: n={len(r)}, first {r[0]:.0f}, "
                     f"best {r.max():.0f} @ {t[r.argmax()]:,}, last {r[-1]:.0f} "
                     f"(final steps {t[-1]:,})\n")
        tail = r[-max(len(r)//10, 3):]
        head_of_tail = r[-max(len(r)//5, 6):-max(len(r)//10, 3)]
        trend = "still rising" if tail.mean() > head_of_tail.mean() + 2 else \
                ("plateaued" if abs(tail.mean() - head_of_tail.mean()) <= 2 else "DECLINING")
        lines.append(f"**late trend**: {trend} "
                     f"(last-10% mean {tail.mean():.0f} vs prior-10% {head_of_tail.mean():.0f})\n")
    except Exception as e:
        lines.append(f"(evaluations.npz unreadable: {e})\n")

    # training curve image
    try:
        name = os.path.basename(D).replace("results_", "")
        dst = os.path.join("training_history", "figs", f"{name}_curve.png")
        shutil.copy(os.path.join(D, "training_curve.png"), dst)
        lines.append(f"\n![training curve](figs/{name}_curve.png)\n")
    except Exception as e:
        lines.append(f"(training_curve.png missing: {e})\n")

    # analysis log: physical eval + dive recovery + traces
    if os.path.exists(analysis):
        txt = open(analysis, encoding="utf-8", errors="replace").read()
        txt = "\n".join(l for l in txt.splitlines()
                        if not re.match(r"^(pybullet|\[INFO\]|argv)", l.strip()))
        for header, title in [("=== PHYSICAL EVAL", "Physical eval"),
                              ("=== DIVE-RECOVERY TEST", "Dive-recovery test")]:
            m = re.search(re.escape(header) + r".*?(?=\n=== |\n--- |\Z)", txt, re.S)
            if m:
                lines.append(f"\n### {title}\n```\n{m.group(0).strip()}\n```\n")
        traces = re.findall(r"--- trace.*?(?=\n--- trace|\n\[ANALYSIS DONE\]|\Z)", txt, re.S)
        if traces:
            lines.append("\n### Behavior traces\n```\n" + "\n".join(t.strip() for t in traces)
                         + "\n```\n")
    else:
        lines.append(f"\n(analysis log not found: {analysis})\n")

    with open(args.md, "a", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[log_trial] appended results of {D} to {args.md}")


if __name__ == "__main__":
    main()
