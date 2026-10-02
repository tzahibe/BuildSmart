"""The PRIMARY run's driver: scores the FROZEN generation dataset against the current generator,
brief by brief, through the identical blind critic (Issue #151, AC-14).

NO LLM CALL, NO NETWORK CALL (AC-14): every LLM proposal comes from `generation_dataset.
load_dataset()` — a committed JSON file already containing every raw response. This module never
imports `llm_client`, `urllib`, `http`, or `socket`, directly or transitively (proven by
`tests/ai_harness/test_topology_no_llm_on_scoring_path.py`, which walks this module's own import
graph). The current generator's own topology is still produced by running the REAL, unmodified
pipeline (`generator_adapter.extract_topology_from_generator`) — that is local computation, not an
LLM or network call.

Mirrors `runner.run_one_brief`'s logic exactly (same schema validation, same exact-duplicate
dedup, same materially-distinct count, same critic, same realizability labelling) — the only
difference is where the raw LLM text comes from.
"""
from __future__ import annotations

import os

from app.ai_harness.topology_poc import (
    briefs as briefs_mod,
    critic,
    duplicates,
    generation_dataset,
    generator_adapter,
    priors as priors_mod,
    realizability as realizability_mod,
    schema,
)
from app.ai_harness.topology_poc.result_types import (
    BriefResult,
    ScoredProposal,
    save_checkpoint,
    score_to_dict,
)
from app.demo.service import DemoGenerationError

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DEFAULT_PRIMARY_CHECKPOINT_PATH = os.path.join(
    _BACKEND_DIR, "..", "docs", "reports", "llm-topology-poc", "primary_run.json")


def _proposals_from_record(record: dict) -> tuple:
    """Replays `record["attempts"]` (already-parsed JSON, no re-parsing of raw text needed) through
    `schema.proposal_from_dict` — the identical validation the live path applies. Stops at the
    first attempt that yields at least one schema-valid proposal, exactly like
    `runner.run_one_brief`'s own one-retry rule."""
    total_generated = 0
    total_rejected = 0
    valid_topologies = []
    model = None
    for attempt in record["attempts"]:
        model = attempt["model"]
        raw_proposals = attempt["parsed_json"].get("proposals", [])
        total_generated += len(raw_proposals)
        for raw in raw_proposals:
            try:
                valid_topologies.append(schema.proposal_from_dict(raw))
            except schema.SchemaViolationError:
                total_rejected += 1
        if valid_topologies:
            break
    return tuple(valid_topologies), total_generated, total_rejected, model


def run_one_brief_from_record(brief, record: dict, priors: priors_mod.Priors) -> BriefResult:
    # 1. current generator's own topology — real local computation, never network/LLM.
    generator_scored = None
    generator_error = None
    try:
        gen_topology = generator_adapter.extract_topology_from_generator(brief.context)
        gen_score = critic.score_topology(gen_topology, priors)
        gen_realizability = realizability_mod.classify_realizability(gen_topology)
        generator_scored = ScoredProposal(
            source=schema.ProposalSource.CURRENT_GENERATOR.value, raw_index=0,
            realizability=gen_realizability.value, score=score_to_dict(gen_score),
            canonical_hash=duplicates.canonical_hash(gen_topology))
    except DemoGenerationError as exc:
        generator_error = f"{exc.code}: {exc.message}"

    # 2. LLM proposals — read from the frozen record, never generated here.
    valid_topologies, total_generated, total_rejected, model = _proposals_from_record(record)

    deduped = duplicates.deduplicate_exact(valid_topologies)
    exact_duplicates = len(valid_topologies) - len(deduped)
    materially_distinct = duplicates.count_materially_distinct(deduped)

    llm_scored = []
    for i, topology in enumerate(deduped):
        score = critic.score_topology(topology, priors)
        label = realizability_mod.classify_realizability(topology)
        llm_scored.append(ScoredProposal(
            source=schema.ProposalSource.LLM.value, raw_index=i, realizability=label.value,
            score=score_to_dict(score), canonical_hash=duplicates.canonical_hash(topology)))

    return BriefResult(
        brief_id=brief.brief_id, source_key=brief.source_key, bedrooms=brief.bedrooms,
        wet_rooms=brief.wet_rooms, safe_room=brief.safe_room, open_plan=brief.open_plan,
        size_tier=brief.size_tier, aspect_tier=brief.aspect_tier,
        generator=generator_scored, generator_error=generator_error,
        llm_proposals=tuple(llm_scored), llm_raw_generated=total_generated,
        llm_schema_rejected=total_rejected, llm_exact_duplicates=exact_duplicates,
        materially_distinct_count=materially_distinct, llm_call_latency_s=None, llm_model=model)


def run_all_briefs_from_dataset(
        dataset_path: str = generation_dataset.DEFAULT_GENERATION_DATASET_JSON) -> dict:
    """Runs every one of the frozen 20 briefs against the frozen dataset. Raises
    `generation_dataset.GenerationDatasetError` if the dataset fails its preflight — never a
    partial or degraded run."""
    dataset = generation_dataset.load_dataset(dataset_path)
    priors = priors_mod.load_priors()
    briefs_by_id = {b.brief_id: b for b in briefs_mod.select_briefs()}

    results = {}
    for record in dataset["records"]:
        brief_id = record["brief_id"]
        brief = briefs_by_id[brief_id]
        results[brief_id] = run_one_brief_from_record(brief, record, priors)
    return results


def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=generation_dataset.DEFAULT_GENERATION_DATASET_JSON)
    parser.add_argument("--checkpoint", default=DEFAULT_PRIMARY_CHECKPOINT_PATH)
    args = parser.parse_args(argv)
    results = run_all_briefs_from_dataset(args.dataset)
    save_checkpoint(args.checkpoint, results)
    print(f"scored {len(results)} briefs from {args.dataset} -> {args.checkpoint}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
