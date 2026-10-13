"""Save Part F controls, timeseries and cache-confusion evidence in a new run directory."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from collections import Counter
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gameday_lab.cache import CachingClient, SemanticCache
from gameday_lab.client import ResilientClient
from gameday_lab.sim.config import load_config
from gameday_lab.sim.contracts import Action, Attempt, CallContext, ProviderError, Serve
from gameday_lab.sim.engine import evaluate_checks, run_scenario
from gameday_lab.sim.faq import INTENTS


class UnfilteredClient(ResilientClient):
    """Intentionally unsafe control, used only by this experiment runner."""

    def ladder(self, task: str) -> list[str]:
        return list(self.order)


class ObservedCacheClient(CachingClient):
    """Record wrong-intent cache hits without changing cache/routing decisions.

    Labels come from the public FAQ catalog, used only for offline diagnostics.
    No simulator private state is read and no labels reach the cache policy.
    """

    def __init__(self, inner: ResilientClient, cache: SemanticCache) -> None:
        super().__init__(inner, cache)
        self.intent_by_text = {text: intent.key for intent in INTENTS for text in intent.texts
                               if intent.source is not None}
        self.origins: dict[int, str] = {}
        self.wrong_hits: list[dict[str, Any]] = []

    def _observe(self, call: CallContext, action: Action, now: float) -> Action:
        if isinstance(action, Serve) and call.request is not None:
            original = self.origins[action.answer.answer_id]
            requested = call.request.text
            if self.intent_by_text[original] != self.intent_by_text[requested]:
                self.wrong_hits.append({"t": now, "requested": requested, "cached_from": original,
                                        "requested_intent": self.intent_by_text[requested],
                                        "cached_intent": self.intent_by_text[original], "stale": action.stale})
        return action

    def start(self, call: CallContext, now: float) -> Action:
        return self._observe(call, super().start(call, now), now)

    def on_error(self, attempt: Attempt, err: ProviderError, now: float) -> Action:
        return self._observe(attempt.call, super().on_error(attempt, err, now), now)

    def on_success(self, attempt: Attempt, now: float, latency_s: float) -> None:
        super().on_success(attempt, now, latency_s)
        call = attempt.call
        if call.request is not None and not call.request.personal and call.answer is not None:
            self.origins[call.answer.answer_id] = call.request.text


def dump(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def table(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=25)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out:
        out = args.out
        out.mkdir(parents=True, exist_ok=False)
    else:
        parent = ROOT / "reports/part_f_runs"
        parent.mkdir(parents=True, exist_ok=True)
        number = 1
        while (parent / f"run_{number:03d}").exists():
            number += 1
        out = parent / f"run_{number:03d}"
        out.mkdir()
    print(f"Results: {out}", flush=True)
    cfg = load_config(ROOT / "configs/gameday.yaml", ROOT / "configs/scenarios.yaml")
    source_files = sorted((ROOT / "src/gameday_lab").rglob("*.py")) + [Path(__file__).resolve()]
    inputs = [ROOT / "configs" / name for name in ("gameday.yaml", "scenarios.yaml", "scenarios_cache.yaml")]
    hashes = {}
    for source in source_files + inputs:
        relative = source.relative_to(ROOT)
        target = out / "source" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[relative.as_posix()] = hashlib.sha256(source.read_bytes()).hexdigest()
    variants = [("reference", deepcopy(cfg.client), list(cfg.scenarios), ResilientClient)]
    for broken in (True, False):
        for budget in (True, False):
            settings = deepcopy(cfg.client)
            settings["max_attempts_per_provider"] = 5
            if broken:
                settings["breaker"]["min_calls"] = 1000000000
            if not budget:
                settings.update(retry_budget_ratio=100, retry_budget_max_tokens=1.0e9,
                                retry_budget_min_per_s=1.0e6)
            label = f"{'broken' if broken else 'working'}_breaker_budget_{'on' if budget else 'off'}"
            variants.append((label, settings, ["G2_overload_storm", "G3_brownout"], ResilientClient))
    variants += [
        ("timeout_30", {**cfg.client, "attempt_timeout_s": 30.0},
         ["G4_slow_region", "G6_provider_outage"], ResilientClient),
        ("without_tool_filter", deepcopy(cfg.client), ["G6_provider_outage"], UnfilteredClient),
    ]
    summary = []
    for label, settings, keys, client_class in variants:
        folder = out / label
        folder.mkdir()
        dump(folder / "settings.json", {"client": settings, "tool_filter": client_class is ResilientClient})
        trial = replace(cfg, client=settings)
        for key in keys:
            client = client_class(trial.provider_infos(), trial.fallback_order, settings, seed=1)
            sim = run_scenario(trial, key, client, args.seed)
            metrics = sim.metrics()
            checks = evaluate_checks(metrics, trial.scenarios[key].checks)
            dump(folder / f"{key}.json", {"seed": args.seed, "metrics": metrics, "checks": checks,
                                          "pass": all(checks.values())})
            table(folder / f"{key}_timeseries.csv", sim.timeseries())
            row = {"experiment": label, "scenario": key, "seed": args.seed, "pass": all(checks.values())}
            for name in ("availability", "latency_p95_s", "amplification", "retry_ratio", "recovery_s",
                         "cost_per_good_turn", "incompatible_routes", "good_turns", "turns"):
                row[name] = metrics[name]
            row["give_up_reasons"] = json.dumps(metrics["give_up_reasons"], sort_keys=True)
            summary.append(row)
            print(label, key, row["availability"], row["latency_p95_s"], row["give_up_reasons"], flush=True)

    # Supplement the Part G aggregate wrong-answer count with actual question
    # pairs, preserving the earlier Part G experiment directory unchanged.
    cache_cfg = load_config(ROOT / "configs/gameday.yaml", ROOT / "configs/scenarios_cache.yaml")
    observed = ObservedCacheClient(
        ResilientClient(cache_cfg.provider_infos(), cache_cfg.fallback_order, cache_cfg.client, seed=1),
        SemanticCache(**{**cache_cfg.cache, "similarity_threshold": 0.80}),
    )
    sim = run_scenario(cache_cfg, "C1_faq_outage", observed, args.seed)
    metrics = sim.metrics()
    if len(observed.wrong_hits) != metrics["wrong_answers_by_reason"].get("other_question", 0):
        raise RuntimeError("Observed wrong-intent count differs from simulator metrics")
    diagnostic = out / "cache_threshold_080_diagnostic"
    diagnostic.mkdir()
    dump(diagnostic / "metrics.json", metrics)
    dump(diagnostic / "settings.json", {"client": cache_cfg.client,
                                         "cache": {**cache_cfg.cache, "similarity_threshold": 0.80}})
    dump(diagnostic / "wrong_hits.json", observed.wrong_hits)
    if observed.wrong_hits:
        table(diagnostic / "wrong_hits.csv", observed.wrong_hits)
    pairs = Counter((hit["requested_intent"], hit["cached_intent"]) for hit in observed.wrong_hits)
    dump(diagnostic / "pairs.json", [{"requested_intent": req, "cached_intent": cached, "count": count}
                                     for (req, cached), count in pairs.most_common()])
    table(out / "summary.csv", summary)
    dump(out / "summary.json", summary)
    dump(out / "manifest.json", {"simulator_seed": args.seed, "client_seed": 1,
                                 "source_and_input_sha256": hashes,
                                 "reference_config": cfg.client,
                                 "wrong_cache_hits_observed": len(observed.wrong_hits)})
    print("Saved", len(summary), "client experiments and", len(observed.wrong_hits), "wrong-cache-hit traces")


if __name__ == "__main__":
    main()
