"""AC-2: the prompt context is built from the corrected #149 artifacts and #140's proportions,
states which roles are unmeasurable, and keeps adjacency and access separate."""
from __future__ import annotations

from app.ai_harness.topology_poc import context, priors


def test_context_built_from_real_corrected_artifacts():
    p = priors.load_priors()
    ctx = context.build_prompt_context(p)
    assert ctx.train_count == p.train_count
    assert ctx.holdout_count == p.holdout_count
    assert ctx.train_count > 0 and ctx.holdout_count > 0


def test_context_states_unmeasurable_roles_explicitly():
    p = priors.load_priors()
    ctx = context.build_prompt_context(p)
    assert "CIRCULATION" in ctx.unmeasurable_roles
    assert "DINING" in ctx.unmeasurable_roles
    assert "MASTER_BEDROOM" in ctx.unmeasurable_roles
    assert "TOILET" in ctx.unmeasurable_roles
    # and the measurable set is disjoint from the unmeasurable set
    assert set(ctx.measurable_roles).isdisjoint(set(ctx.unmeasurable_roles))


def test_adjacency_and_access_facts_are_kept_in_separate_fields():
    p = priors.load_priors()
    ctx = context.build_prompt_context(p)
    assert ctx.adjacency_facts != ()
    assert ctx.access_facts != ()
    # they are genuinely different measurements, not the same numbers copy-pasted twice
    adjacency_rates = {(f.role_a, f.role_b): f.rate for f in ctx.adjacency_facts}
    access_rates = {(f.role_a, f.role_b): f.rate for f in ctx.access_facts}
    shared_pairs = set(adjacency_rates) & set(access_rates)
    assert shared_pairs, "expected at least one pair measurable under both semantics"
    assert any(adjacency_rates[pair] != access_rates[pair] for pair in shared_pairs) or (
        set(adjacency_rates) != set(access_rates))


def test_rendered_text_states_adjacency_is_not_access():
    p = priors.load_priors()
    ctx = context.build_prompt_context(p)
    text = context.render_context_text(ctx)
    assert "ADJACENCY IS NOT ACCESS" in text
    assert "SPATIAL ADJACENCY facts" in text
    assert "ACCESS facts" in text


def test_rendered_text_includes_room_proportion_notes():
    p = priors.load_priors()
    ctx = context.build_prompt_context(p)
    text = context.render_context_text(ctx)
    assert "room proportions" in text.lower()
    assert len(ctx.room_proportion_notes) > 0
