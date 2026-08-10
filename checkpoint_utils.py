"""Checkpoint-pair utilities for PPO weights and VecNormalize state.

A policy checkpoint is not reproducible without the observation-normalization statistics from
the same timestep.  This module makes that pairing explicit and verifies bundle hashes when a
manifest is present.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import warnings


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save_vecnormalize_atomic(env, path: str) -> None:
    """Save VecNormalize to a temporary sibling, then atomically replace ``path``."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".vecnormalize-", suffix=".tmp", dir=directory)
    os.close(fd)
    try:
        env.save(tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def write_checkpoint_manifest(directory: str, model_path: str, vecnormalize_path: str,
                              timestep: int, mean_reward=None, config_path=None,
                              manifest_name="checkpoint.json") -> str:
    """Write the manifest last, so its presence means the checkpoint pair is complete."""
    os.makedirs(directory, exist_ok=True)
    if config_path and os.path.exists(config_path):
        dst = os.path.join(directory, "config.json")
        if os.path.abspath(config_path) != os.path.abspath(dst):
            shutil.copy2(config_path, dst)
    data = {
        "format": 1,
        "timestep": int(timestep),
        "model": os.path.basename(model_path),
        "vecnormalize": os.path.basename(vecnormalize_path),
        "model_sha256": sha256_file(model_path),
        "vecnormalize_sha256": sha256_file(vecnormalize_path),
    }
    if mean_reward is not None:
        data["mean_eval_reward"] = float(mean_reward)
    target = os.path.join(directory, manifest_name)
    fd, tmp = tempfile.mkstemp(prefix=".checkpoint-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return target


def _require_pair(model_path: str, vecnormalize_path: str, label: str):
    missing = [p for p in (model_path, vecnormalize_path) if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError(f"{label} checkpoint is incomplete; missing: {missing}")
    return model_path, vecnormalize_path, label


def _verify_manifest(directory: str, model_path: str, vecnormalize_path: str) -> None:
    manifest = os.path.join(directory, "checkpoint.json")
    if not os.path.exists(manifest):
        return
    with open(manifest, encoding="utf-8") as f:
        data = json.load(f)
    expected = {
        "model_sha256": sha256_file(model_path),
        "vecnormalize_sha256": sha256_file(vecnormalize_path),
    }
    for key, actual in expected.items():
        if data.get(key) != actual:
            raise ValueError(f"checkpoint manifest hash mismatch for {key} in {directory}")


def resolve_checkpoint(directory: str, checkpoint="auto", model_file=None,
                       vecnormalize_file=None):
    """Resolve a reproducible model/normalization pair.

    ``auto`` uses a complete paired best bundle when available and otherwise uses the matching
    final pair. ``legacy-best`` is the only mode that permits the historical best-weights plus
    final-normalization mismatch, and emits a warning.
    """
    if (model_file is None) != (vecnormalize_file is None):
        raise ValueError("--model-file and --vecnormalize-file must be supplied together")
    if model_file is not None:
        return _require_pair(model_file, vecnormalize_file, "explicit")

    best_model = os.path.join(directory, "best", "best_model.zip")
    best_norm = os.path.join(directory, "best", "vecnormalize.pkl")
    final_model = os.path.join(directory, "ppo_ratevel_final.zip")
    final_norm = os.path.join(directory, "vecnormalize.pkl")

    if checkpoint == "auto":
        if os.path.exists(best_model) and os.path.exists(best_norm):
            checkpoint = "best"
        else:
            checkpoint = "final"
            if os.path.exists(best_model):
                warnings.warn(
                    f"{directory} has legacy best weights but no matching VecNormalize; "
                    "using the reproducible final pair. Use checkpoint='legacy-best' only "
                    "to reproduce historical mixed-pair reports.", RuntimeWarning)
    if checkpoint == "best":
        pair = _require_pair(best_model, best_norm, "best")
        _verify_manifest(os.path.join(directory, "best"), pair[0], pair[1])
        return pair
    if checkpoint == "final":
        return _require_pair(final_model, final_norm, "final")
    if checkpoint == "legacy-best":
        warnings.warn("using best PPO weights with final VecNormalize statistics; this is not "
                      "a reproducible checkpoint pair", RuntimeWarning)
        return _require_pair(best_model, final_norm, "legacy-best")
    raise ValueError(f"unknown checkpoint mode: {checkpoint}")
