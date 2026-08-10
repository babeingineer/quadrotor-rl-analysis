"""Select a reproducible checkpoint by worst-band 0–45 m/s physical performance.

Mean reward can hide a failed speed band. This tool evaluates every periodic model with its
matching VecNormalize state on fixed, held-out episodes in six command-speed bands. It minimizes
the worst band median first and pooled median second, then emits an atomic ``envelope_best``
bundle plus a complete JSON audit trail.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil

import numpy as np

from checkpoint_utils import sha256_file, write_checkpoint_manifest
from eval_velyaw import load


BANDS = (
    ("hover", 0.0, 1.0),
    ("low", 1.0, 10.0),
    ("mid", 10.0, 18.0),
    ("high", 18.0, 25.0),
    ("vhigh", 25.0, 34.0),
    ("top", 34.0, 45.0),
)
MODEL_RE = re.compile(r"^ppo_ratevel_(\d+)_steps\.zip$")
NORM_RE = re.compile(r"^ppo_ratevel_vecnormalize_(\d+)_steps\.pkl$")


def discover(directory):
    directory = Path(directory)
    ckpts = directory / "ckpts"
    models, norms = {}, {}
    if ckpts.exists():
        for p in ckpts.iterdir():
            m = MODEL_RE.match(p.name)
            if m:
                models[int(m.group(1))] = p
            m = NORM_RE.match(p.name)
            if m:
                norms[int(m.group(1))] = p
    candidates = [
        {"label": f"periodic-{step}", "step": step, "model": str(models[step]),
         "vecnormalize": str(norms[step])}
        for step in sorted(models.keys() & norms.keys())
    ]
    best_manifest = directory / "best" / "checkpoint.json"
    if best_manifest.exists():
        data = json.loads(best_manifest.read_text(encoding="utf-8"))
        candidates.append({"label": "reward-best", "step": int(data["timestep"]),
                           "model": str(directory / "best" / "best_model.zip"),
                           "vecnormalize": str(directory / "best" / "vecnormalize.pkl")})
    final_model, final_norm = directory / "ppo_ratevel_final.zip", directory / "vecnormalize.pkl"
    if final_model.exists() and final_norm.exists():
        final_manifest = directory / "checkpoint_final.json"
        step = -1
        if final_manifest.exists():
            step = int(json.loads(final_manifest.read_text(encoding="utf-8"))["timestep"])
        candidates.append({"label": "final", "step": step, "model": str(final_model),
                           "vecnormalize": str(final_norm)})
    if not candidates:
        raise FileNotFoundError(f"no paired checkpoints found in {directory}")
    return candidates


def evaluate_candidate(directory, candidate, episodes_per_band, ep_len, steady_window,
                       seed_base):
    model, venv, base = load(
        directory, ep_len=ep_len, model_file=candidate["model"],
        vecnormalize_file=candidate["vecnormalize"])
    if base.MAX_SPEED < BANDS[-1][2]:
        raise ValueError(f"policy MAX_SPEED={base.MAX_SPEED} does not cover 0–45 m/s")
    dt = base.CTRL_TIMESTEP
    steps = int(ep_len / dt)
    steady_start = steps - int(steady_window / dt)
    failure_error = 2.0 * base.MAX_SPEED
    metrics, pooled = {}, []
    for band_index, (name, lo, hi) in enumerate(BANDS):
        base.set_target_speed_range(lo, hi)
        errors, crashes = [], 0
        for i in range(episodes_per_band):
            venv.seed(seed_base + band_index * 1000 + i)
            obs = venv.reset()
            model.reset()
            tail, early = [], False
            for k in range(steps):
                action, _ = model.predict(obs, deterministic=True)
                obs, _, done, infos = venv.step(action)
                if k >= steady_start:
                    tail.append(infos[0]["vel_error"])
                if done[0]:
                    early = k < steps - 1
                    break
            if early or not tail:
                crashes += 1
                errors.append(failure_error)
            else:
                errors.append(float(np.mean(tail)))
        values = np.asarray(errors)
        pooled.extend(errors)
        metrics[name] = {
            "range": [lo, hi], "n": episodes_per_band,
            "mean": float(values.mean()), "median": float(np.median(values)),
            "pct_under_1": float(100.0 * np.mean(values < 1.0)),
            "p90": float(np.percentile(values, 90)), "crashes": crashes,
        }
    venv.close()
    pooled = np.asarray(pooled)
    worst_median = max(v["median"] for v in metrics.values())
    result = dict(candidate)
    result.update({
        "model_sha256": sha256_file(candidate["model"]),
        "vecnormalize_sha256": sha256_file(candidate["vecnormalize"]),
        "bands": metrics,
        "worst_band_median": float(worst_median),
        "pooled_median": float(np.median(pooled)),
        "pooled_pct_under_1": float(100.0 * np.mean(pooled < 1.0)),
        "total_crashes": int(sum(v["crashes"] for v in metrics.values())),
    })
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--episodes-per-band", type=int, default=5)
    ap.add_argument("--ep-len", type=float, default=8.0)
    ap.add_argument("--steady-window", type=float, default=3.0)
    ap.add_argument("--seed-base", type=int, default=17300)
    args = ap.parse_args()
    if args.episodes_per_band < 1:
        ap.error("--episodes-per-band must be positive")

    candidates = discover(args.dir)
    results = []
    for index, candidate in enumerate(candidates, 1):
        print(f"[{index}/{len(candidates)}] {candidate['label']} step={candidate['step']}",
              flush=True)
        result = evaluate_candidate(
            args.dir, candidate, args.episodes_per_band, args.ep_len,
            args.steady_window, args.seed_base)
        results.append(result)
        print(f"  worst={result['worst_band_median']:.3f} "
              f"pooled={result['pooled_median']:.3f} "
              f"<1={result['pooled_pct_under_1']:.1f}% crashes={result['total_crashes']}",
              flush=True)

    # Crashes dominate first, then minimize the worst band and pooled median. This selection
    # objective matches "works across the whole envelope" rather than maximizing an average.
    selected = min(results, key=lambda r: (
        r["total_crashes"], r["worst_band_median"], r["pooled_median"],
        -r["pooled_pct_under_1"]))
    out = Path(args.dir) / "envelope_best"
    out.mkdir(parents=True, exist_ok=True)
    model_out, norm_out = out / "best_model.zip", out / "vecnormalize.pkl"
    shutil.copy2(selected["model"], model_out)
    shutil.copy2(selected["vecnormalize"], norm_out)
    config_path = Path(args.dir) / "config.json"
    write_checkpoint_manifest(
        str(out), str(model_out), str(norm_out), selected["step"],
        config_path=str(config_path))
    audit = {
        "selection_rule": ["total_crashes", "worst_band_median", "pooled_median",
                           "negative_pooled_pct_under_1"],
        "episodes_per_band": args.episodes_per_band,
        "ep_len": args.ep_len,
        "steady_window": args.steady_window,
        "seed_base": args.seed_base,
        "selected_label": selected["label"],
        "selected_step": selected["step"],
        "results": results,
    }
    (out / "selection.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"SELECTED {selected['label']} step={selected['step']} -> {out}")


if __name__ == "__main__":
    main()
