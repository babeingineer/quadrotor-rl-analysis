"""Run two fresh seeds of the Trial 73 basin-only winner without overwriting Trial 73."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys


STATUS_PATH = Path("xw74_status.json")


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
    ap.add_argument("--seeds", type=int, nargs="+", default=[7401, 7402])
    ap.add_argument("--timesteps", type=int, default=4_000_000)
    ap.add_argument("--episodes", type=int, default=600)
    ap.add_argument("--selection-episodes-per-band", type=int, default=5)
    ap.add_argument("--recovery-episodes", type=int, default=120)
    args = ap.parse_args()

    if len(set(args.seeds)) != len(args.seeds):
        raise ValueError("replication seeds must be unique")
    common = [
        "--xwing-aero", "--max-speed", "45", "--speed-min", "0",
        "--wind-max", "15", "--yaw-bias", "0.3", "--yaw-gate",
        "--yaw-att-gate", "--vel-precision", "0.7", "--cov-width", "5",
        "--ent-coef", "0.003", "--att-cmd", "--katt", "1.5", "--trim-init", "0.2",
        "--integral-tau", "3", "--gamma", "0.99", "--episode-len", "8",
        "--n-envs", "6", "--timesteps", str(args.timesteps), "--device", "cpu",
        "--rel-basin", "1.0",
    ]
    status = {
        "state": "running", "pid": os.getpid(), "started_at": timestamp(),
        "updated_at": timestamp(), "timesteps_per_seed": args.timesteps,
        "seeds": {str(seed): {"state": "pending"} for seed in args.seeds},
    }
    save_status(status)
    try:
        for seed in args.seeds:
            key = str(seed)
            out = Path(f"results_velyaw_xw74_basin_s{seed}")
            if out.exists():
                raise FileExistsError(f"refusing to overwrite replication: {out}")
            status["current_seed"] = seed
            status["seeds"][key] = {"state": "training", "started_at": timestamp()}
            status["updated_at"] = timestamp()
            save_status(status)

            run_logged(
                [sys.executable, "train.py", *common, "--seed", str(seed),
                 "--out-dir", str(out)],
                f"{out}_train.log",
            )
            status["seeds"][key]["state"] = "selecting"
            status["updated_at"] = timestamp()
            save_status(status)
            run_logged(
                [sys.executable, "select_envelope_checkpoint.py", "--dir", str(out),
                 "--episodes-per-band", str(args.selection_episodes_per_band),
                 "--seed-base", "17300"],
                f"{out}_selection.log",
            )

            selected_model = out / "envelope_best" / "best_model.zip"
            selected_norm = out / "envelope_best" / "vecnormalize.pkl"
            status["seeds"][key]["state"] = "evaluating"
            status["updated_at"] = timestamp()
            save_status(status)
            run_logged(
                [sys.executable, "evaluate_envelope.py", "--dir", str(out),
                 "--model-file", str(selected_model), "--vecnormalize-file", str(selected_norm),
                 "--episodes-per-band", str(max(1, args.episodes // 6)),
                 "--seed-base", "27300"],
                f"{out}_physical.log",
            )
            run_logged(
                [sys.executable, "analyze_velyaw.py", "--dir", str(out),
                 "--episodes", str(args.recovery_episodes), "--model-file", str(selected_model),
                 "--vecnormalize-file", str(selected_norm)],
                f"{out}_recovery.log",
            )
            status["seeds"][key]["state"] = "complete"
            status["seeds"][key]["completed_at"] = timestamp()
            status["updated_at"] = timestamp()
            save_status(status)

        status["state"] = "complete"
        status.pop("current_seed", None)
        status["completed_at"] = timestamp()
        status["updated_at"] = timestamp()
        save_status(status)
    except Exception as exc:
        status["state"] = "failed"
        status["error"] = f"{type(exc).__name__}: {exc}"
        if "current_seed" in status:
            status["seeds"][str(status["current_seed"])]["state"] = "failed"
        status["updated_at"] = timestamp()
        save_status(status)
        raise


if __name__ == "__main__":
    main()
