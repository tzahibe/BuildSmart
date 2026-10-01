"""Orchestrates one brief end to end: current-generator topology + N LLM proposals, all scored by
the SAME critic (Issue #151, requirements 4-9). Resumable/chunkable by design (requirement: this
POC's own 20-brief run must fit inside a 10-minute-per-command sandbox) — `run_briefs` writes a
checkpoint JSON after every brief and `--resume` skips briefs already present in it.

BLIND TO SOURCE, END TO END: `critic.score_topology` is always called on a bare `TopologyProposal`
(never on `ScoredProposal`/`BriefResult`, which are this module's OWN result-bookkeeping types and
carry `source`/`realizability` as plain strings for the report, never passed back into the critic).
See `critic.py`'s own docstring for the test that proves the critic itself cannot see a `source`.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

from app.ai_harness.topology_poc import (
    briefs as briefs_mod,
    context as context_mod,
    critic,
    duplicates,
    generator_adapter,
    llm_client,
    llm_parsing,
    priors as priors_mod,
    prompt as prompt_mod,
    realizability as realizability_mod,
    schema,
)
from app.ai_harness.topology_poc.result_types import (
    BriefResult,
    ScoredProposal,
    load_checkpoint,
    save_checkpoint,
    score_to_dict as _score_dict,
)
from app.demo.service import DemoGenerationError

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DEFAULT_CHECKPOINT_PATH = os.path.join(
    _BACKEND_DIR, "..", "docs", "reports", "llm-topology-poc", "raw_run.json")

N_PROPOSALS_PER_BRIEF = 8


def run_one_brief(brief: briefs_mod.Brief, priors: priors_mod.Priors,
                  context: context_mod.PromptContext, *, n_proposals: int = N_PROPOSALS_PER_BRIEF
                  ) -> BriefResult:
    # 1. current generator's own topology
    generator_scored = None
    generator_error = None
    try:
        gen_topology = generator_adapter.extract_topology_from_generator(brief.context)
        gen_score = critic.score_topology(gen_topology, priors)
        gen_realizability = realizability_mod.classify_realizability(gen_topology)
        generator_scored = ScoredProposal(
            source=schema.ProposalSource.CURRENT_GENERATOR.value, raw_index=0,
            realizability=gen_realizability.value, score=_score_dict(gen_score),
            canonical_hash=duplicates.canonical_hash(gen_topology))
    except DemoGenerationError as exc:
        generator_error = f"{exc.code}: {exc.message}"

    # 2. LLM proposals. A local 3B model's compliance varies call to call (temperature=0.6) — one
    # retry when the first call yields zero USABLE (schema-valid) proposals, never more than that:
    # this measures "can the model do it at all", not "keep hammering until it does".
    system_prompt, user_prompt = prompt_mod.build_prompt(context, brief, n_proposals=n_proposals)
    total_generated = 0
    total_rejected = 0
    valid_topologies = []
    call = None
    for _attempt in range(2):
        call = llm_client.generate(user_prompt, system_prompt=system_prompt)
        outcome = llm_parsing.parse_proposals_array(call.text)
        total_generated += outcome.elements_seen
        for raw in outcome.raw_dicts:
            try:
                valid_topologies.append(schema.proposal_from_dict(raw))
            except schema.SchemaViolationError:
                total_rejected += 1
        if valid_topologies:
            break
    schema_rejected = total_rejected

    deduped = duplicates.deduplicate_exact(tuple(valid_topologies))
    exact_duplicates = len(valid_topologies) - len(deduped)
    materially_distinct = duplicates.count_materially_distinct(deduped)

    llm_scored = []
    for i, topology in enumerate(deduped):
        score = critic.score_topology(topology, priors)
        label = realizability_mod.classify_realizability(topology)
        llm_scored.append(ScoredProposal(
            source=schema.ProposalSource.LLM.value, raw_index=i, realizability=label.value,
            score=_score_dict(score), canonical_hash=duplicates.canonical_hash(topology)))

    return BriefResult(
        brief_id=brief.brief_id, source_key=brief.source_key, bedrooms=brief.bedrooms,
        wet_rooms=brief.wet_rooms, safe_room=brief.safe_room, open_plan=brief.open_plan,
        size_tier=brief.size_tier, aspect_tier=brief.aspect_tier,
        generator=generator_scored, generator_error=generator_error,
        llm_proposals=tuple(llm_scored), llm_raw_generated=total_generated,
        llm_schema_rejected=schema_rejected, llm_exact_duplicates=exact_duplicates,
        materially_distinct_count=materially_distinct, llm_call_latency_s=call.latency_s,
        llm_model=call.model)


def run_briefs(*, start: int = 0, limit: "int | None" = None, resume: bool = True,
              checkpoint_path: str = DEFAULT_CHECKPOINT_PATH,
              n_proposals: int = N_PROPOSALS_PER_BRIEF) -> dict:
    priors = priors_mod.load_priors()
    context = context_mod.build_prompt_context(priors)
    all_briefs = briefs_mod.select_briefs()

    results = load_checkpoint(checkpoint_path) if resume else {}
    target = all_briefs[start:start + limit] if limit is not None else all_briefs[start:]
    for brief in target:
        if resume and brief.brief_id in results:
            continue
        t0 = time.time()
        result = run_one_brief(brief, priors, context, n_proposals=n_proposals)
        results[brief.brief_id] = result
        save_checkpoint(checkpoint_path, results)
        print(f"{brief.brief_id}: {len(result.llm_proposals)} LLM proposals kept "
             f"(generated {result.llm_raw_generated}, rejected {result.llm_schema_rejected}, "
             f"exact-dup {result.llm_exact_duplicates}), materially_distinct="
             f"{result.materially_distinct_count}, {time.time() - t0:.1f}s", file=sys.stderr)
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT_PATH)
    parser.add_argument("--n-proposals", type=int, default=N_PROPOSALS_PER_BRIEF)
    args = parser.parse_args(argv)
    run_briefs(start=args.start, limit=args.limit, resume=not args.no_resume,
              checkpoint_path=args.checkpoint, n_proposals=args.n_proposals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
