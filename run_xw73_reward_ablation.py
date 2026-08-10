"""Pre-registered 0–45 m/s reward screen.

Four fresh, matched PPO policies; one reward mechanism changes per arm. This runner is prepared
by trial 72 but is intentionally not auto-launched.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


ARMS = {
    "legacy": [],
    "linear": ["--cmd-linear"],
    "basin": ["--rel-basin", "1.0"],
    "both": ["--cmd-linear", "--rel-basin", "1.0"],
}
STATUS_PATH = Path("xw73_status.json")


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def save_status(status):
    tmp = STATUS_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, STATUS_PATH)


def run_logged(command, path):
    with open(path, "w", encoding="utf-8") as log:
        subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--timesteps", type=int, default=4_000_000)
    ap.add_argument("--episodes", type=int, default=600)
    ap.add_argument("--selection-episodes-per-band", type=int, default=5)
    ap.add_argument("--recovery-episodes", type=int, default=120)
    ap.add_argument("--seed", type=int, default=7300)
    ap.add_argument("--only", choices=tuple(ARMS), default=None,
                    help="run one arm (mainly for smoke/debug); default runs all four")
    args = ap.parse_args()

    common = [
        "--xwing-aero", "--max-speed", "45", "--speed-min", "0",
        "--wind-max", "15", "--yaw-bias", "0.3", "--yaw-gate",
        "--yaw-att-gate", "--vel-precision", "0.7", "--cov-width", "5",
        "--ent-coef", "0.003", "--att-cmd", "--katt", "1.5", "--trim-init", "0.2",
        "--integral-tau", "3", "--gamma", "0.99", "--episode-len", "8",
        "--n-envs", "6", "--timesteps", str(args.timesteps), "--device", "cpu",
    ]
    selected = [args.only] if args.only else list(ARMS)
    status = {
        "state": "running", "pid": os.getpid(), "started_at": timestamp(),
        "updated_at": timestamp(), "timesteps_per_arm": args.timesteps,
        "seed": args.seed, "selected_arms": selected,
        "arms": {name: {"state": "pending"} for name in selected},
    }
    save_status(status)
    try:
        for name in selected:
            out = Path(f"results_velyaw_xw73_{name}")
            if out.exists():
                raise FileExistsError(f"refusing to overwrite existing arm: {out}")
            status["current_arm"] = name
            status["arms"][name] = {"state": "training", "started_at": timestamp()}
            status["updated_at"] = timestamp(); save_status(status)
            train_cmd = [sys.executable, "train.py", *common, "--seed", str(args.seed),
                         "--out-dir", str(out), *ARMS[name]]
            run_logged(train_cmd, f"{out}_train.log")

            status["arms"][name]["state"] = "selecting"
            status["updated_at"] = timestamp(); save_status(status)
            run_logged([sys.executable, "select_envelope_checkpoint.py", "--dir", str(out),
                        "--episodes-per-band", str(args.selection_episodes_per_band)],
                       f"{out}_selection.log")
            selected_model = out / "envelope_best" / "best_model.zip"
            selected_norm = out / "envelope_best" / "vecnormalize.pkl"

            status["arms"][name]["state"] = "evaluating"
            status["updated_at"] = timestamp(); save_status(status)
            run_logged([sys.executable, "evaluate_envelope.py", "--dir", str(out),
                        "--model-file", str(selected_model), "--vecnormalize-file",
                        str(selected_norm), "--episodes-per-band",
                        str(max(1, args.episodes // 6))], f"{out}_physical.log")
            run_logged([sys.executable, "analyze_velyaw.py", "--dir", str(out),
                        "--episodes", str(args.recovery_episodes), "--model-file",
                        str(selected_model), "--vecnormalize-file", str(selected_norm)],
                       f"{out}_recovery.log")
            status["arms"][name]["state"] = "complete"
            status["arms"][name]["completed_at"] = timestamp()
            status["updated_at"] = timestamp(); save_status(status)
        status["state"] = "complete"
        status.pop("current_arm", None)
        status["completed_at"] = timestamp()
        status["updated_at"] = timestamp(); save_status(status)
    except Exception as exc:
        status["state"] = "failed"
        status["error"] = f"{type(exc).__name__}: {exc}"
        if status.get("current_arm"):
            status["arms"][status["current_arm"]]["state"] = "failed"
        status["updated_at"] = timestamp(); save_status(status)
        raise


if __name__ == "__main__":
    main()
