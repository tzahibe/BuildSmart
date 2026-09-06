"""LocalArchitectModelGateway: runs the accepted Architect Model V1 (Qwen2.5-Coder-7B-Instruct + LoRA)
in-process, reproducing — not reinventing — the exact prompt/generation contract verified against the
fine-tuning project's own `src/evaluation/prompts.py` and `src/evaluation/run_final_holdout.py`:

- chat-format system+user messages (verbatim `SYSTEM_PROMPT` below, byte-for-byte the same template,
  substituted with this same codebase's own `ModelRoomType`/`ModelZoneType`/`ModelRelationshipType`
  values — see `model_schema.py`, itself copied from the verified `src/datasets/schema.py`)
- `tokenizer.apply_chat_template(messages, add_generation_prompt=True)`
- greedy decoding (`do_sample=False`), `max_new_tokens` from config (verified default: 2048)
- raw generated text decoded directly, then parsed as JSON (balanced-brace extraction, tolerant of a
  markdown fence even though the real model doesn't emit one in practice) and validated as a
  `ModelArchitecturalSpec` — i.e. the model's OWN schema, not BuildSmart's. `app/architect/adapter.py`
  is the only place that gets translated into BuildSmart's `ArchitecturalSpec`.

Only imported (and only loads `torch`/`transformers`/`peft`, and the 7B model itself) when
`ARCHITECT_MODEL_PROVIDER=local` is actually selected — see `app/architect/gateway.py`'s factory.
"""

import json
import logging
import re

from pydantic import ValidationError

from app.architect.adapter import adapt_model_spec, model_room_type_for
from app.architect.config import LocalArchitectModelConfig
from app.architect.errors import (
    ArchitectModelEmptyResponseError,
    ArchitectModelInvalidOutputError,
    ArchitectModelMalformedJSONError,
)
from app.architect.gateway import ArchitectModelGateway
from app.architect.model_schema import ModelArchitecturalSpec, ModelRelationshipType, ModelRoomType, ModelZoneType
from app.architect.models import ArchitecturalSpec, ArchitectModelRequest, RequiredRoomConstraint, RequirementState

logger = logging.getLogger("buildsmart.architect_local_gateway")

# Verbatim from the fine-tuning project's src/evaluation/prompts.py — do not edit without re-verifying
# against that source. The enum value lists are substituted from this codebase's own model_schema.py,
# which is itself a verbatim copy of the training project's src/datasets/schema.py enums.
_SYSTEM_PROMPT = """You are an architectural planning assistant. Given a residential \
Brief (what the user wants), a Site (the physical plot), and a set of Constraints \
(facts the design must satisfy), output an Architectural SPEC as a single JSON object.

The SPEC must have exactly these top-level keys: "program", "zones", "relationships", "circulation".

- "program": list of {{"type": ROOM_TYPE, "count": int > 0, "area_per_room_m2": float > 0, "zone": ZONE_TYPE}}
  one entry per distinct room type in the design. "area_per_room_m2" is the area of
  ONE room of that type (not a total).
- "zones": list of {{"type": ZONE_TYPE, "room_types": [ROOM_TYPE, ...]}} grouping room
  types by zone.
- "relationships": list of {{"a_type": ROOM_TYPE, "b_type": ROOM_TYPE, "relationship": RELATIONSHIP_TYPE}}
  describing functional connections between room types.
- "circulation": list of ROOM_TYPE values that serve circulation (e.g. staircases).

Valid ROOM_TYPE values: {room_types}
Valid ZONE_TYPE values: {zone_types}
Valid RELATIONSHIP_TYPE values: {relationship_types}

Respond with ONLY the JSON object. No markdown code fences, no explanation, no \
reasoning before or after it.""".format(
    room_types=", ".join(t.value for t in ModelRoomType),
    zone_types=", ".join(t.value for t in ModelZoneType),
    relationship_types=", ".join(t.value for t in ModelRelationshipType),
)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _build_model_input(request: ArchitectModelRequest) -> dict:
    """The input-side counterpart to `adapter.py`: reshapes BuildSmart's own `ArchitectModelRequest`
    into the exact `{"brief", "site", "constraints"}` dict the verified prompt expects (matching
    `src/datasets/sft_format.py::to_sft_pair()`'s `input` shape). A `RequiredRoomConstraint` with no
    representation in the model's real vocabulary (today: only "safe_room" — see `model_schema.py`) is
    left out entirely rather than sent as a value the model's own schema doesn't define; an "unknown"
    room count is also left out (matches the model's own "absent constraint = no opinion" semantics) —
    BOTH are still enforced afterwards by `app/architect/authoritative_merge.py`, independent of
    whatever the model does with an under-specified prompt.
    """
    brief: dict = {"building_type": "residential"}
    bedroom_constraint = next(
        (
            c
            for c in request.hard_constraints
            if isinstance(c, RequiredRoomConstraint) and c.room_type == "bedroom" and c.state == RequirementState.known
        ),
        None,
    )
    if bedroom_constraint is not None:
        brief["bedrooms"] = bedroom_constraint.count
    if request.target_area_m2 is not None:
        brief["target_area_m2"] = request.target_area_m2

    site = {
        "width_m": request.site.width_m,
        "length_m": request.site.depth_m,
        # BuildSmart's current site is always a square (see app/design/pipeline.py's
        # `site_side_m = sqrt(plot_area_m2)`), so width_m * depth_m reproduces plot_area_m2 exactly —
        # not an approximation.
        "area_m2": round(request.site.width_m * request.site.depth_m, 2),
    }

    constraints: list[dict] = []
    if request.target_area_m2 is not None:
        # Matches the verified training data's own shape: brief.target_area_m2 and a redundant
        # TOTAL_AREA/SOFT/USER_REQUIREMENT constraint consistently appear together (see
        # docs/DATA_CONTRACT.md in the fine-tuning project) — this isn't a new field BuildSmart invented.
        constraints.append(
            {
                "type": "TOTAL_AREA",
                "value": request.target_area_m2,
                "unit": "m2",
                "priority": "SOFT",
                "source_type": "USER_REQUIREMENT",
            }
        )
    for constraint in request.hard_constraints:
        if not isinstance(constraint, RequiredRoomConstraint) or constraint.state != RequirementState.known:
            continue
        model_room_type = model_room_type_for(constraint.room_type)
        if model_room_type is None:
            continue  # e.g. "safe_room" — no ConstraintType/RoomType target this model was trained on
        constraints.append(
            {
                "type": "ROOM_COUNT",
                "target": model_room_type.value,
                "value": float(constraint.count or 0),
                "priority": "HARD",
                "source_type": "USER_REQUIREMENT",
            }
        )

    return {"brief": brief, "site": site, "constraints": constraints}


def _build_messages(model_input: dict) -> list[dict]:
    """Verbatim logic from `src/evaluation/prompts.py::build_prompt()`."""
    user_content = "Brief:\n" + json.dumps(model_input["brief"], indent=2)
    user_content += "\n\nSite:\n" + json.dumps(model_input["site"], indent=2)
    user_content += "\n\nConstraints:\n" + json.dumps(model_input["constraints"], indent=2)
    user_content += "\n\nReturn the Architectural SPEC as a single JSON object."

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _extract_json_object(raw_text: str) -> str:
    """Same balanced-brace extraction as the verified evaluation path's `src/evaluation/metrics.py
    ::extract_json()` (strips a markdown fence if present, takes the first balanced {...} block) — the
    real model doesn't emit fences in practice (verified: 500/500 real holdout generations, plus 3/3 of
    this integration's own fresh real-inference runs, were bare JSON), but this stays tolerant of one
    rather than assuming it can never happen.
    """
    text = raw_text.strip()
    fence_match = _JSON_FENCE_RE.search(text)
    if fence_match:
        text = fence_match.group(1).strip()

    start = text.find("{")
    if start == -1:
        raise ArchitectModelMalformedJSONError("Architect Model (local) output contained no '{' at all")

    depth = 0
    end = None
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        raise ArchitectModelMalformedJSONError("Architect Model (local) output had unbalanced braces")

    return text[start:end]


def _parse_model_output(raw_text: str) -> ModelArchitecturalSpec:
    if not raw_text or not raw_text.strip():
        raise ArchitectModelEmptyResponseError("Architect Model (local) returned an empty response")

    json_text = _extract_json_object(raw_text)
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as error:
        raise ArchitectModelMalformedJSONError(f"Architect Model (local) output was not valid JSON: {error}") from error

    try:
        return ModelArchitecturalSpec.model_validate(parsed)
    except ValidationError as error:
        raise ArchitectModelInvalidOutputError(
            f"Architect Model (local) output did not match the real model's own schema: {error}"
        ) from error


class LocalArchitectModelGateway(ArchitectModelGateway):
    def __init__(
        self,
        config: LocalArchitectModelConfig,
        *,
        tokenizer=None,
        model=None,
        device: str | None = None,
    ) -> None:
        """`tokenizer`/`model`/`device` are an injectable seam for tests (mirrors
        `RealArchitectModelGateway`'s injectable `httpx.Client`) — pass all three to exercise `generate()`
        end-to-end against a fake model/tokenizer with no `torch`/`transformers`/`peft` import at all.
        Leaving them unset (the real, production path) is what actually loads the 7B model."""
        self._config = config
        # Diagnostics from the most recent generate() call — a side-channel `getattr(gateway,
        # "last_diagnostics", [])` read by app/design/pipeline.py for DesignVersion.adapter_diagnostics.
        # Doesn't change generate()'s own return value/contract at all; Mock/Real gateways simply don't
        # have this attribute, which the getattr default handles.
        self.last_diagnostics: list[str] = []
        if tokenizer is not None and model is not None and device is not None:
            self._tokenizer, self._model, self._device = tokenizer, model, device
            return

        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        if torch.cuda.is_available():
            resolved_device = "cuda"
        elif torch.backends.mps.is_available():
            resolved_device = "mps"
        else:
            resolved_device = "cpu"

        self._tokenizer = AutoTokenizer.from_pretrained(config.base_model_id)
        base_model = AutoModelForCausalLM.from_pretrained(config.base_model_id, dtype=torch.bfloat16).to(resolved_device)
        self._model = PeftModel.from_pretrained(base_model, config.adapter_path).to(resolved_device)
        self._model.eval()
        self._device = resolved_device

    def generate(self, request: ArchitectModelRequest) -> ArchitecturalSpec:
        import torch

        model_input = _build_model_input(request)
        messages = _build_messages(model_input)
        prompt_text = self._tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self._tokenizer(prompt_text, return_tensors="pt").to(self._device)

        with torch.no_grad():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=self._config.max_new_tokens,
                do_sample=False,
                temperature=None,
                top_p=None,
                top_k=None,
                pad_token_id=self._tokenizer.eos_token_id,
            )
        new_tokens = output_ids[0][inputs["input_ids"].shape[1] :]
        raw_text = self._tokenizer.decode(new_tokens, skip_special_tokens=True)

        model_spec = _parse_model_output(raw_text)
        result = adapt_model_spec(model_spec)
        for diagnostic in result.diagnostics:
            logger.info("architect_model_adapter_diagnostic %s", diagnostic)
        self.last_diagnostics = list(result.diagnostics)
        return result.spec
