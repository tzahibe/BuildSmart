"""JSON schemas for the structured outputs every agent role must return.

Passed to `claude -p --json-schema`, so a run that does not end in a document of this shape is a
failed run — the orchestrator never scrapes free text for a verdict.
"""
from __future__ import annotations

WORKER_REPORT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["done", "blocked", "needs_decision"]},
        "summary": {"type": "string"},
        "what_changed": {"type": "array", "items": {"type": "string"}},
        "why": {"type": "string"},
        "implementation": {"type": "string"},
        "ac_evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ac": {"type": "string"},
                    "evidence": {"type": "string"},
                    "result": {"type": "string", "enum": ["PASS", "FAIL", "NOT_VERIFIED"]},
                },
                "required": ["ac", "evidence", "result"],
            },
        },
        "tests_run": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"command": {"type": "string"}, "result": {"type": "string"}},
                "required": ["command", "result"],
            },
        },
        "regression": {"type": "string"},
        "known_limitations": {"type": "array", "items": {"type": "string"}},
        "files_changed": {"type": "array", "items": {"type": "string"}},
        "documentation_changes": {"type": "string"},
        "blockers": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["status", "summary", "what_changed", "why", "implementation", "ac_evidence", "tests_run",
                 "regression", "known_limitations", "files_changed", "blockers"],
}

REVIEW_VERDICT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["APPROVE", "REQUEST_CHANGES", "BLOCK"]},
        "summary": {"type": "string"},
        "ac_assessment": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ac": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["MET", "NOT_MET", "UNCLEAR"]},
                    "note": {"type": "string"},
                },
                "required": ["ac", "verdict", "note"],
            },
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["blocker", "major", "minor", "nit"]},
                    "file": {"type": "string"},
                    "line": {"type": ["integer", "null"]},
                    "summary": {"type": "string"},
                },
                "required": ["severity", "file", "summary"],
            },
        },
        "unrelated_changes": {"type": "boolean"},
        "hidden_behavior_changes": {"type": "boolean"},
        "tolerance_hacks": {"type": "boolean"},
        "silent_fallback": {"type": "boolean"},
        "tests_meaningful": {"type": "boolean"},
        "architecture_appropriate": {"type": "boolean"},
        "architectural_assessment": {
            "type": "object",
            "description": "rubric section (e.g. 'A. Room Proportion & Aspect Ratio') -> a short note "
                            "on how this PR was judged against it; {} when the architectural reference "
                            "did not apply to this PR's domains.",
            "additionalProperties": {"type": "string"},
        },
        "overfits_one_plan": {
            "type": "boolean",
            "description": "true if the change only helps the repro context and would not generalize, "
                            "or trades a real gain for hidden regression elsewhere. An APPROVE with this "
                            "true is downgraded to REQUEST_CHANGES by the orchestrator.",
        },
    },
    "required": ["verdict", "summary", "ac_assessment", "findings", "unrelated_changes", "hidden_behavior_changes",
                 "tolerance_hacks", "silent_fallback", "tests_meaningful", "architecture_appropriate",
                 "architectural_assessment", "overfits_one_plan"],
}

DOMAIN_LEAD_BRIEF_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "string"}},
        "recommended_approach": {"type": "string"},
        "alternatives": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "affected_modules": {"type": "array", "items": {"type": "string"}},
        "suggested_acceptance_criteria": {"type": "array", "items": {"type": "string"}},
        "suggested_verification": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "needs_product_decision": {"type": "boolean"},
    },
    "required": ["summary", "findings", "recommended_approach", "risks", "affected_modules",
                 "suggested_acceptance_criteria", "open_questions", "needs_product_decision"],
}
