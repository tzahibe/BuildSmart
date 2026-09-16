"""The local-model suitability benchmark. Run directly:

    uv run python -m tests.ai_harness.bench

Benchmarks every installed, completion-capable Ollama model (today: `llama3.2`, `gemma4:26b` —
never a 3rd, unpulled candidate) against the golden dataset, sequentially (never two models
concurrently, and never alongside a planner sweep — see docs/AI_TEST_HARNESS.md's RAM policy for
why). Writes:

  reports/benchmark_latest.json      — full measured results, per-topic breakdown, best-effort memory
  reports/model_recommendation.json  — the LOCAL_FAST / LOCAL_STRONG verdicts tests/ai_harness/config.py
                                        reads by default (an explicit AI_TEST_LOCAL_*_MODEL env var
                                        always overrides this)

Does not call OpenAI — the production column is always reported NOT MEASURED unless a caller
explicitly opts in (not wired here, by design — see docs/AI_TEST_HARNESS.md).
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime

from app.local_models.discovery import discover_ollama
from tests.ai_harness.config import ollama_base_url_from_env
from tests.ai_harness.golden_dataset import SYSTEM_PROMPT, build_prompt, extract_json, load_cases, score_response
from tests.ai_harness.providers.ollama_provider import OllamaTestLLMProvider

REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
MIN_ACCEPTABLE_FIELD_ACCURACY = 0.5


def _ollama_rss_mb() -> float | None:
    """Best-effort, macOS/Linux `ps`-based RSS sample of the Ollama server process(es). Never
    raises — memory observation is a nice-to-have, not a hard requirement."""
    try:
        pids = subprocess.run(["pgrep", "-f", "ollama"], capture_output=True, text=True).stdout.split()
        if not pids:
            return None
        total_kb = 0
        for pid in pids:
            r = subprocess.run(["ps", "-o", "rss=", "-p", pid], capture_output=True, text=True)
            total_kb += int((r.stdout or "0").strip() or 0)
        return round(total_kb / 1024, 1)
    except Exception:
        return None


def benchmark_model(model_name: str, base_url: str, cases: list) -> dict:
    provider = OllamaTestLLMProvider(model_name, base_url)
    per_topic: dict[str, dict] = {}
    n_exact = n_invalid = 0
    latencies, field_scores = [], []

    for case in cases:
        response = provider.complete(build_prompt(case), system_prompt=SYSTEM_PROMPT)
        latencies.append(response.latency_ms)
        result = score_response(case, extract_json(response.text))
        n_invalid += int(result.invalid_json)
        n_exact += int(result.exact_match)
        field_scores.append(result.field_accuracy)

        bucket = per_topic.setdefault(case.topic, {"n": 0, "exact": 0, "field_acc_sum": 0.0})
        bucket["n"] += 1
        bucket["exact"] += int(result.exact_match)
        bucket["field_acc_sum"] += result.field_accuracy

    n = len(cases) or 1
    return {
        "model": model_name,
        "n_cases": len(cases),
        "exact_accuracy": n_exact / n,
        "field_accuracy": sum(field_scores) / n,
        "invalid_json_rate": n_invalid / n,
        "latency_ms_avg": sum(latencies) / n if latencies else 0.0,
        "latency_ms_max": max(latencies) if latencies else 0.0,
        "per_topic": {
            t: {"n": b["n"], "exact_accuracy": b["exact"] / b["n"], "field_accuracy": b["field_acc_sum"] / b["n"]}
            for t, b in per_topic.items()
        },
    }


def _topic_split(name: str, results: dict) -> tuple[dict[str, float], dict[str, float]]:
    """(reliable_topics, weak_topics) — the SAME MIN_ACCEPTABLE_FIELD_ACCURACY threshold applied
    per topic instead of only to the aggregate. An aggregate score can clear the bar while most of
    its individual topics don't; this is what catches that (see LOCAL_FAST_LIMITED below)."""
    per_topic = results[name].get("per_topic", {})
    reliable = {t: v["field_accuracy"] for t, v in per_topic.items() if v["field_accuracy"] >= MIN_ACCEPTABLE_FIELD_ACCURACY}
    weak = {t: v["field_accuracy"] for t, v in per_topic.items() if v["field_accuracy"] < MIN_ACCEPTABLE_FIELD_ACCURACY}
    return reliable, weak


def _verdict(role: str, name: str, results: dict) -> dict:
    acc = results[name]["field_accuracy"]
    if acc < MIN_ACCEPTABLE_FIELD_ACCURACY:
        return {"verdict": "NOT_SUITABLE", "model": name, "field_accuracy": acc,
                 "reason": f"measured field_accuracy {acc:.2f} below {MIN_ACCEPTABLE_FIELD_ACCURACY} threshold"}

    reliable, weak = _topic_split(name, results)
    if role == "local_fast" and weak:
        # An aggregate above the bar does NOT mean "generally suitable" if most individual topics
        # are below it — that would let a model coast on the few topics it happens to be good at.
        # LOCAL_FAST_LIMITED surfaces the split explicitly rather than collapsing it into one label.
        return {
            "verdict": "LOCAL_FAST_LIMITED", "model": name, "field_accuracy": acc,
            "reliable_topics": reliable, "weak_topics": weak,
            "reason": (
                f"aggregate field_accuracy {acc:.2f} clears {MIN_ACCEPTABLE_FIELD_ACCURACY}, but "
                f"{len(weak)}/{len(reliable) + len(weak)} topics do not ({', '.join(sorted(weak))}) "
                f"— not a generally reliable LOCAL_FAST model; usable only for reliable_topics "
                f"without further evidence."
            ),
        }
    return {"verdict": role.upper(), "model": name, "field_accuracy": acc,
            "reliable_topics": reliable, **({"weak_topics": weak} if weak else {})}


def _recommend(results: dict[str, dict]) -> dict:
    if not results:
        reason = "Ollama unavailable or no completion-capable models installed"
        return {
            "local_fast": {"verdict": "NOT_SUITABLE", "reason": reason},
            "local_strong": {"verdict": "NOT_SUITABLE", "reason": reason},
        }

    names_by_size_order = list(results.keys())  # inserted smallest-first by run_benchmark
    fast_name = names_by_size_order[0]
    strong_name = names_by_size_order[-1]

    return {"local_fast": _verdict("local_fast", fast_name, results),
            "local_strong": _verdict("local_strong", strong_name, results)}


def run_benchmark() -> dict:
    base_url = ollama_base_url_from_env()
    status = discover_ollama(base_url)
    cases = load_cases()

    results: dict[str, dict] = {}
    memory: dict[str, dict] = {}
    if status.available:
        candidates = sorted(status.completion_capable_models, key=lambda m: m.size_bytes)
        for m in candidates:
            # Sequential, never concurrent — see module docstring's RAM policy.
            mem_before = _ollama_rss_mb()
            result = benchmark_model(m.name, base_url, cases)
            result["ram_caution"] = m.ram_caution
            result["parameter_size"] = m.parameter_size
            results[m.name] = result
            memory[m.name] = {"rss_mb_before": mem_before, "rss_mb_after": _ollama_rss_mb()}

    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "ollama_available": status.available,
        "models_benchmarked": list(results.keys()),
        "third_candidate_note": "only 2 models installed (llama3.2, gemma4:26b) — a 3rd was not pulled without approval",
        "results": results,
        "memory_rss_mb": memory,
        "production_model": "NOT MEASURED — not run this session (would require real OpenAI API calls)",
    }

    os.makedirs(REPORTS_DIR, exist_ok=True)
    with open(os.path.join(REPORTS_DIR, "benchmark_latest.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    with open(os.path.join(REPORTS_DIR, "model_recommendation.json"), "w", encoding="utf-8") as f:
        json.dump(_recommend(results), f, indent=2)

    return report


if __name__ == "__main__":
    print(json.dumps(run_benchmark(), indent=2, ensure_ascii=False))
