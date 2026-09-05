"""Tests for `app/architect/local_gateway.py`. `test_generate_end_to_end_*` inject a fake
tokenizer/model (see `_FakeTokenizer`/`_FakeModel` below) so the full `generate()` path — prompt
construction, greedy-decoding call shape, JSON extraction, adapter integration — is exercised without
loading the real 7B model. The one thing NOT re-verified here is that the real model actually produces
this raw text for this prompt — that's what this milestone's live real-inference run (against the
actual base model + LoRA adapter) already established; see the final report's "one full real trace."
"""

import json

import pytest

from app.architect.config import LocalArchitectModelConfig
from app.architect.errors import (
    ArchitectModelEmptyResponseError,
    ArchitectModelInvalidOutputError,
    ArchitectModelMalformedJSONError,
)
from app.architect.local_gateway import (
    _SYSTEM_PROMPT,
    LocalArchitectModelGateway,
    _build_messages,
    _build_model_input,
    _parse_model_output,
)
from app.architect.models import ArchitectModelRequest, ConstraintSeverity, RequiredRoomConstraint, RequirementState, SiteSpec

_REAL_RAW_OUTPUT = (
    '{"program": [{"type": "BALCONY", "count": 1, "area_per_room_m2": 3.5, "zone": "OUTDOOR"}, '
    '{"type": "BATHROOM", "count": 1, "area_per_room_m2": 9.0, "zone": "SERVICE"}, '
    '{"type": "BEDROOM", "count": 2, "area_per_room_m2": 14.0, "zone": "PRIVATE"}, '
    '{"type": "KITCHEN", "count": 1, "area_per_room_m2": 6.0, "zone": "SERVICE"}, '
    '{"type": "LIVING", "count": 1, "area_per_room_m2": 23.0, "zone": "PUBLIC"}], '
    '"zones": [{"type": "PRIVATE", "room_types": ["BEDROOM"]}, {"type": "PUBLIC", "room_types": ["LIVING"]}, '
    '{"type": "SERVICE", "room_types": ["BATHROOM", "KITCHEN"]}, {"type": "OUTDOOR", "room_types": ["BALCONY"]}], '
    '"relationships": [{"a_type": "KITCHEN", "b_type": "LIVING", "relationship": "ADJACENT", "source_type": "OBSERVED_GEOMETRY"}], '
    '"circulation": []}'
)


def _request(
    *, bedroom_state=RequirementState.known, bedroom_count=2, include_safe_room=False, target_area_m2=None
) -> ArchitectModelRequest:
    hard = [RequiredRoomConstraint(room_type="bedroom", state=bedroom_state, count=bedroom_count, severity=ConstraintSeverity.hard)]
    if include_safe_room:
        hard.append(RequiredRoomConstraint(room_type="safe_room", state=RequirementState.known, count=1, severity=ConstraintSeverity.hard))
    return ArchitectModelRequest(
        brief="ignored", site=SiteSpec(width_m=10.0, depth_m=8.0), target_area_m2=target_area_m2, hard_constraints=hard
    )


# --- Input-side mapping (BuildSmart request -> the model's real input shape) ----------------------


def test_build_model_input_includes_known_bedroom_count_as_room_count_constraint():
    model_input = _build_model_input(_request(bedroom_count=3))

    assert model_input["brief"]["bedrooms"] == 3
    assert model_input["constraints"] == [
        {"type": "ROOM_COUNT", "target": "BEDROOM", "value": 3.0, "priority": "HARD", "source_type": "USER_REQUIREMENT"}
    ]


def test_build_model_input_omits_unknown_bedroom_entirely():
    model_input = _build_model_input(_request(bedroom_state=RequirementState.unknown, bedroom_count=None))

    assert "bedrooms" not in model_input["brief"]
    assert model_input["constraints"] == []


def test_build_model_input_never_sends_a_safe_room_constraint():
    # The real model's ConstraintType/RoomType vocabulary has no SAFE_ROOM target at all — sending one
    # would be a value the model's own schema doesn't define, not a real constraint it could act on.
    model_input = _build_model_input(_request(include_safe_room=True))

    assert all(c["target"] != "SAFE_ROOM" for c in model_input["constraints"])
    assert len(model_input["constraints"]) == 1  # only the bedroom ROOM_COUNT constraint


def test_build_model_input_site_area_matches_width_times_depth():
    model_input = _build_model_input(_request())

    assert model_input["site"] == {"width_m": 10.0, "length_m": 8.0, "area_m2": 80.0}


def test_build_model_input_includes_target_area_m2_in_brief_and_as_a_total_area_constraint():
    # Real product validation surfaced that omitting this entirely leaves the model with no area
    # anchor at all, and it was observed producing wildly oversized rooms as a result (e.g. a 125 m²
    # living room for a 70 m² house) — see app/architect/models.py's `target_area_m2` docstring.
    model_input = _build_model_input(_request(bedroom_count=2, target_area_m2=70.0))

    assert model_input["brief"]["target_area_m2"] == 70.0
    assert {"type": "TOTAL_AREA", "value": 70.0, "unit": "m2", "priority": "SOFT", "source_type": "USER_REQUIREMENT"} in model_input[
        "constraints"
    ]


def test_build_model_input_omits_target_area_when_not_given():
    model_input = _build_model_input(_request(target_area_m2=None))

    assert "target_area_m2" not in model_input["brief"]
    assert all(c["type"] != "TOTAL_AREA" for c in model_input["constraints"])


# --- Prompt construction (must reproduce the verified contract exactly, never invent a new prompt) ----


def test_system_prompt_matches_the_verified_contract_and_has_no_safe_room_vocabulary():
    assert 'The SPEC must have exactly these top-level keys: "program", "zones", "relationships", "circulation".' in _SYSTEM_PROMPT
    assert "Respond with ONLY the JSON object. No markdown code fences" in _SYSTEM_PROMPT
    assert "BEDROOM" in _SYSTEM_PROMPT
    assert "SAFE_ROOM" not in _SYSTEM_PROMPT  # the real model's vocabulary has no such value


def test_build_messages_shape():
    model_input = _build_model_input(_request())
    messages = _build_messages(model_input)

    assert messages[0] == {"role": "system", "content": _SYSTEM_PROMPT}
    assert messages[1]["role"] == "user"
    assert "Brief:" in messages[1]["content"]
    assert "Site:" in messages[1]["content"]
    assert "Constraints:" in messages[1]["content"]
    assert messages[1]["content"].endswith("Return the Architectural SPEC as a single JSON object.")


# --- Raw-output parsing --------------------------------------------------------------------------


def test_parse_model_output_valid():
    model_spec = _parse_model_output(_REAL_RAW_OUTPUT)
    assert len(model_spec.program) == 5


def test_parse_model_output_tolerates_a_markdown_fence_even_though_the_real_model_does_not_emit_one():
    model_spec = _parse_model_output(f"```json\n{_REAL_RAW_OUTPUT}\n```")
    assert len(model_spec.program) == 5


def test_parse_model_output_empty_raises_empty_response_error():
    with pytest.raises(ArchitectModelEmptyResponseError):
        _parse_model_output("")


def test_parse_model_output_malformed_json_raises_malformed_json_error():
    with pytest.raises(ArchitectModelMalformedJSONError):
        _parse_model_output("{not valid json")


def test_parse_model_output_schema_invalid_raises_invalid_output_error():
    with pytest.raises(ArchitectModelInvalidOutputError):
        _parse_model_output(json.dumps({"foo": "bar"}))


# --- Full generate() via an injected fake tokenizer/model (no torch/transformers I/O) ---------------


class _FakeArray:
    def __init__(self, data):
        self._data = data

    @property
    def shape(self):
        return (1, len(self._data))

    def __getitem__(self, index):
        return self._data[index]


class _FakeInputs(dict):
    def to(self, device):
        return self


class _FakeTokenizer:
    def __init__(self, raw_output_text: str):
        self.raw_output_text = raw_output_text
        self.eos_token_id = 0
        self.last_messages = None

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        self.last_messages = messages
        return "FAKE_PROMPT_TEXT"

    def __call__(self, text, return_tensors=None):
        return _FakeInputs({"input_ids": _FakeArray([1, 2, 3])})

    def decode(self, tokens, skip_special_tokens=True):
        return self.raw_output_text


class _FakeOutputIds:
    def __init__(self, length: int):
        self._length = length

    def __getitem__(self, index):
        return list(range(self._length))


class _FakeModel:
    def __init__(self):
        self.last_generate_kwargs = None

    def generate(self, **kwargs):
        self.last_generate_kwargs = kwargs
        return _FakeOutputIds(10)


def _gateway_with_fakes(raw_output_text: str) -> tuple[LocalArchitectModelGateway, _FakeTokenizer, _FakeModel]:
    config = LocalArchitectModelConfig(base_model_id="fake/model", adapter_path="fake/adapter", max_new_tokens=2048)
    tokenizer = _FakeTokenizer(raw_output_text)
    model = _FakeModel()
    gateway = LocalArchitectModelGateway(config, tokenizer=tokenizer, model=model, device="cpu")
    return gateway, tokenizer, model


def test_generate_end_to_end_returns_an_adapted_architectural_spec():
    gateway, tokenizer, model = _gateway_with_fakes(_REAL_RAW_OUTPUT)

    spec = gateway.generate(_request(bedroom_count=2))

    room_types = {item.room_type for item in spec.program}
    assert room_types == {"balcony", "bathroom", "bedroom", "kitchen", "living_room"}
    assert spec.circulation is None  # never fabricated from the model's own circulation field
    assert all(item.source == "MODEL_INFERENCE" for item in spec.program)


def test_generate_uses_the_verified_generation_parameters():
    gateway, tokenizer, model = _gateway_with_fakes(_REAL_RAW_OUTPUT)

    gateway.generate(_request())

    assert model.last_generate_kwargs["do_sample"] is False
    assert model.last_generate_kwargs["max_new_tokens"] == 2048
    assert model.last_generate_kwargs["temperature"] is None
    assert model.last_generate_kwargs["top_p"] is None
    assert model.last_generate_kwargs["top_k"] is None


def test_generate_applies_the_chat_template_with_add_generation_prompt():
    gateway, tokenizer, model = _gateway_with_fakes(_REAL_RAW_OUTPUT)

    gateway.generate(_request(bedroom_count=3))

    assert tokenizer.last_messages[0]["role"] == "system"
    assert tokenizer.last_messages[1]["role"] == "user"
    assert '"bedrooms": 3' in tokenizer.last_messages[1]["content"]


def test_generate_propagates_typed_errors_for_bad_output():
    gateway, tokenizer, model = _gateway_with_fakes("not json at all")

    with pytest.raises(ArchitectModelMalformedJSONError):
        gateway.generate(_request())
