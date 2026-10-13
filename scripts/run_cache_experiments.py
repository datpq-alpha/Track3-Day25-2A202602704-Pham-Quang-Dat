"""Run Part G controls and sensitivity experiments without overwriting earlier runs.

Example (after activating the virtual environment):
    python scripts/run_cache_experiments.py --similarity-threshold 0.9 --ttl-s 30 --max-stale-s 300

Each run snapshots source/configuration and writes metrics plus timeseries for
every experiment/seed. A future comparison can use --reference-config with an
earlier run's input_config.yaml.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gameday_lab.factory import build_client
from gameday_lab.sim.config import load_config
from gameday_lab.sim.engine import evaluate_checks, run_scenario


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def reserve_output(requested: Path | None) -> Path:
    if requested is not None:
        requested.mkdir(parents=True, exist_ok=False)
        return requested
    parent = ROOT / "reports" / "part_g_runs"
    parent.mkdir(parents=True, exist_ok=True)
    number = 1
    while True:
        path = parent / f"run_{number:03d}"
        try:
            path.mkdir()
            return path
        except FileExistsError:
            number += 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/gameday.yaml")
    parser.add_argument("--scenarios", type=Path, default=ROOT / "configs/scenarios_cache.yaml")
    parser.add_argument("--reference-config", type=Path)
    parser.add_argument("--seeds", default="25,26,27")
    parser.add_argument("--client-seed", type=int, default=1)
    parser.add_argument("--similarity-threshold", type=float)
    parser.add_argument("--ttl-s", type=float)
    parser.add_argument("--max-stale-s", type=float)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    seeds = list(dict.fromkeys(int(seed) for seed in args.seeds.split(",")))
    cfg = load_config(args.config, args.scenarios)
    chosen = dict(cfg.cache)
    for name in ("similarity_threshold", "ttl_s", "max_stale_s"):
        value = getattr(args, name)
        if value is not None:
            chosen[name] = value
    reference_path = args.reference_config or args.config
    reference = load_config(reference_path, args.scenarios).cache
    variants = {
        "no_cache": None,
        "reference_cache": reference,
        "chosen": chosen,
        "threshold_080": {**chosen, "similarity_threshold": 0.80},
        "threshold_097": {**chosen, "similarity_threshold": 0.97},
        "ttl_030": {**chosen, "ttl_s": 30.0},
        "ttl_060": {**chosen, "ttl_s": 60.0},
        "ttl_300": {**chosen, "ttl_s": 300.0},
        "no_stale": {**chosen, "max_stale_s": 0.0},
    }
    out = reserve_output(args.out)
    print(f"Results: {out}", flush=True)
    shutil.copyfile(args.config, out / "input_config.yaml")
    shutil.copyfile(args.scenarios, out / "scenarios_cache.yaml")
    shutil.copyfile(reference_path, out / "reference_config.yaml")
    # Full source snapshots make historical numbers interpretable even after
    # the cache/client/simulator or this runner changes in a future iteration.
    source_files = sorted((ROOT / "src/gameday_lab").rglob("*.py"))
    source_files += [Path(__file__).resolve()]
    hashes = {}
    for source in source_files:
        relative = source.relative_to(ROOT)
        target = out / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[relative.as_posix()] = hashlib.sha256(source.read_bytes()).hexdigest()
    manifest: dict[str, Any] = {
        "created_at": datetime.now(timezone(timedelta(hours=7))).isoformat(),
        "timezone": "Asia/Saigon",
        "python": sys.version,
        "command": sys.argv,
        "seeds": seeds,
        "client_seed": args.client_seed,
        "client_settings": cfg.client,
        "chosen_cache_settings": chosen,
        "source_sha256": hashes,
        "input_sha256": {
            name: hashlib.sha256((out / name).read_bytes()).hexdigest()
            for name in ("input_config.yaml", "scenarios_cache.yaml", "reference_config.yaml")
        },
        "experiments": {},
    }
    write_json(out / "manifest.json", manifest)
    summary = []
    completed: dict[str, str] = {}
    chosen_passed = True
    for label, cache_settings in variants.items():
        signature = json.dumps(cache_settings, sort_keys=True)
        if signature in completed:
            manifest["experiments"][label] = {"alias_of": completed[signature]}
            continue
        completed[signature] = label
        client_name = "resilient" if cache_settings is None else "cached"
        trial = replace(cfg, cache=cache_settings if cache_settings is not None else cfg.cache)
        experiment_dir = out / label
        experiment_dir.mkdir()
        write_json(experiment_dir / "settings.json", {"client": cfg.client, "cache": cache_settings})
        manifest["experiments"][label] = {"client": client_name, "cache": cache_settings}
        for seed in seeds:
            seed_dir = experiment_dir / f"seed_{seed}"
            seed_dir.mkdir()
            for key, scenario in trial.scenarios.items():
                sim = run_scenario(trial, key, build_client(client_name, trial, args.client_seed), seed)
                metrics = sim.metrics()
                checks = evaluate_checks(metrics, scenario.checks)
                passed = all(checks.values())
                write_json(seed_dir / f"{key}.json", {"seed": seed, "metrics": metrics,
                                                     "checks": checks, "pass": passed})
                write_csv(seed_dir / f"{key}_timeseries.csv", sim.timeseries())
                row = {"experiment": label, "seed": seed, "scenario": key, "pass": passed}
                for name in ("availability", "faq_availability", "cache_hit_ratio", "stale_served",
                             "wrong_answers", "outdated_answers", "cost_per_good_turn", "latency_p95_s"):
                    row[name] = metrics[name]
                row["wrong_answers_by_reason"] = json.dumps(metrics["wrong_answers_by_reason"], sort_keys=True)
                summary.append(row)
                print(label, seed, "PASS" if passed else "FAIL",
                      f"faq={metrics['faq_availability']:.4f} hit={metrics['cache_hit_ratio']:.3f}",
                      f"wrong={metrics['wrong_answers']} outdated={metrics['outdated_answers']}", flush=True)
                if label == "chosen":
                    chosen_passed = chosen_passed and passed
    # chosen can be an alias when the input configuration is already final.
    chosen_label = manifest["experiments"]["chosen"].get("alias_of", "chosen")
    chosen_passed = all(row["pass"] for row in summary if row["experiment"] == chosen_label)
    write_json(out / "summary.json", summary)
    write_csv(out / "summary.csv", summary)
    manifest["chosen_passed"] = chosen_passed
    write_json(out / "manifest.json", manifest)
    print(f"Chosen configuration: {'PASS' if chosen_passed else 'FAIL'}; saved to {out}")
    if not chosen_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
