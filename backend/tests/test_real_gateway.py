"""Tests for RealArchitectModelGateway using stubbed inference responses (httpx.MockTransport) — no
real network calls, no dependency on Architect Model V1 actually being reachable. See
app/architect/real_gateway.py's module docstring for why the wire protocol these stubs exercise is a
documented placeholder, not a confirmed real contract.
"""

import httpx
import pytest

from app.architect.config import RealArchitectModelConfig
from app.architect.errors import (
    ArchitectModelEmptyResponseError,
    ArchitectModelInvalidOutputError,
    ArchitectModelMalformedJSONError,
    ArchitectModelTimeoutError,
    ArchitectModelUnavailableError,
)
from app.architect.models import AdjacencyConstraint, ArchitectModelRequest, SiteSpec
from app.architect.real_gateway import RealArchitectModelGateway

_CONFIG = RealArchitectModelConfig(base_url="https://model.invalid/generate", model_id="v1", api_key="secret-token", timeout_s=5)

_VALID_SPEC_JSON = """
{
  "program": [
    {"room_type": "kitchen", "count": 1, "target_area_m2": 12.0, "min_width_m": 2.4},
    {"room_type": "living_room", "count": 1, "target_area_m2": 20.0, "min_width_m": 3.0}
  ],
  "zones": [{"name": "public", "room_types": ["kitchen", "living_room"], "cohesion_severity": "soft"}],
  "relationships": [
    {"kind": "adjacency", "room_type_a": "kitchen", "room_type_b": "living_room", "severity": "hard"}
  ],
  "circulation": {"entry_room_type": "living_room", "requires_hallway": false},
  "incomplete_requirements": []
}
"""


def _request() -> ArchitectModelRequest:
    return ArchitectModelRequest(brief="test brief", site=SiteSpec(width_m=12, depth_m=10))


def _gateway_with_transport(handler) -> RealArchitectModelGateway:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return RealArchitectModelGateway(_CONFIG, client=client)


# --- Happy path ------------------------------------------------------------------------------


def test_valid_model_response_produces_a_matching_architectural_spec():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret-token"
        return httpx.Response(200, json={"output": _VALID_SPEC_JSON})

    gateway = _gateway_with_transport(handler)

    spec = gateway.generate(_request())

    assert [item.room_type for item in spec.program] == ["kitchen", "living_room"]
    assert spec.circulation.entry_room_type == "living_room"
    assert len(spec.relationships) == 1
    assert isinstance(spec.relationships[0], AdjacencyConstraint)


def test_valid_model_response_wrapped_in_a_markdown_json_fence_is_still_parsed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"output": f"Here is the plan:\n```json\n{_VALID_SPEC_JSON}\n```"})

    gateway = _gateway_with_transport(handler)

    spec = gateway.generate(_request())

    assert len(spec.program) == 2


def test_payload_is_a_direct_unrenamed_serialization_of_the_request():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"output": _VALID_SPEC_JSON})

    gateway = _gateway_with_transport(handler)
    gateway.generate(_request())

    assert captured["body"]["model"] == "v1"
    assert captured["body"]["input"]["brief"] == "test brief"
    assert captured["body"]["input"]["site"] == {"width_m": 12.0, "depth_m": 10.0}


# --- Distinct failure classes ------------------------------------------------------------------


def test_empty_response_raises_empty_response_error():
    gateway = _gateway_with_transport(lambda r: httpx.Response(200, json={"output": ""}))

    with pytest.raises(ArchitectModelEmptyResponseError):
        gateway.generate(_request())


def test_malformed_json_raises_malformed_json_error():
    gateway = _gateway_with_transport(lambda r: httpx.Response(200, json={"output": "{not valid json"}))

    with pytest.raises(ArchitectModelMalformedJSONError):
        gateway.generate(_request())


def test_schema_invalid_json_raises_invalid_output_error():
    # Valid JSON, but missing every required ArchitecturalSpec field.
    gateway = _gateway_with_transport(lambda r: httpx.Response(200, json={"output": '{"foo": "bar"}'}))

    with pytest.raises(ArchitectModelInvalidOutputError):
        gateway.generate(_request())


def test_unsupported_relationship_kind_raises_invalid_output_error():
    spec_with_bad_kind = """
    {
      "program": [{"room_type": "kitchen", "count": 1, "target_area_m2": 12.0}],
      "zones": [],
      "relationships": [
        {"kind": "telepathic_link", "room_type_a": "kitchen", "room_type_b": "kitchen", "severity": "hard"}
      ],
      "circulation": {"entry_room_type": "kitchen"}
    }
    """
    gateway = _gateway_with_transport(lambda r: httpx.Response(200, json={"output": spec_with_bad_kind}))

    with pytest.raises(ArchitectModelInvalidOutputError):
        gateway.generate(_request())


def test_timeout_raises_timeout_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    gateway = _gateway_with_transport(handler)

    with pytest.raises(ArchitectModelTimeoutError):
        gateway.generate(_request())


def test_connection_failure_raises_unavailable_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    gateway = _gateway_with_transport(handler)

    with pytest.raises(ArchitectModelUnavailableError):
        gateway.generate(_request())


def test_server_error_status_raises_unavailable_error():
    gateway = _gateway_with_transport(lambda r: httpx.Response(503, text="Service Unavailable"))

    with pytest.raises(ArchitectModelUnavailableError):
        gateway.generate(_request())


def test_client_error_status_raises_invalid_output_error():
    gateway = _gateway_with_transport(lambda r: httpx.Response(400, json={"error": "bad request"}))

    with pytest.raises(ArchitectModelInvalidOutputError):
        gateway.generate(_request())


def test_non_json_http_response_raises_malformed_json_error():
    gateway = _gateway_with_transport(lambda r: httpx.Response(200, text="not json at all"))

    with pytest.raises(ArchitectModelMalformedJSONError):
        gateway.generate(_request())
