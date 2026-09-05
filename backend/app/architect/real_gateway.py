"""RealArchitectModelGateway: calls an external Architect Model V1 inference endpoint over HTTP.

*** WIRE PROTOCOL STATUS: UNCONFIRMED PLACEHOLDER — READ BEFORE RELYING ON THIS ***

No Architect Model V1 API documentation, sample request/response pair, or live endpoint was available
in the environment this was built in. The request envelope, response envelope, and JSON-extraction
logic below are a reasonable, narrowly-isolated placeholder based on common inference-serving
conventions (a JSON POST carrying the model input; a JSON response carrying generated text that itself
contains an `ArchitecturalSpec` as JSON, optionally wrapped in a ```json fence). Exactly two functions
encode this assumption — `_build_payload` and `_extract_architectural_spec` — so that once the real
model's actual documented contract is available, only those two need to change; nothing else in this
class, and nothing in the rest of BuildSmart, depends on the wire format. Do not treat this as verified
against the real model — it has not been.

Regardless of wire format, this gateway's contract with the rest of BuildSmart is fixed and enforced
here: it receives an `ArchitectModelRequest`, and returns ONLY a fully-validated `ArchitecturalSpec`, or
raises one of `app.architect.errors`'s typed exceptions. No raw model JSON/dict/text ever propagates
past `generate()` — see that method.
"""

import json
import re

import httpx
from pydantic import ValidationError

from app.architect.config import RealArchitectModelConfig
from app.architect.errors import (
    ArchitectModelEmptyResponseError,
    ArchitectModelInvalidOutputError,
    ArchitectModelMalformedJSONError,
    ArchitectModelTimeoutError,
    ArchitectModelUnavailableError,
)
from app.architect.gateway import ArchitectModelGateway
from app.architect.models import ArchitecturalSpec, ArchitectModelRequest

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _build_payload(request: ArchitectModelRequest, model_id: str | None) -> dict:
    """UNCONFIRMED placeholder envelope — see module docstring. A direct, unrenamed serialization of
    `ArchitectModelRequest` (no invented prompt template, no field renaming) wrapped in a minimal
    `{model?, input}` envelope."""
    payload: dict = {"input": request.model_dump(mode="json")}
    if model_id:
        payload["model"] = model_id
    return payload


def _extract_json_text(raw_text: str) -> str:
    fence_match = _JSON_FENCE_RE.search(raw_text)
    return fence_match.group(1).strip() if fence_match else raw_text.strip()


def _extract_architectural_spec(response_body: dict) -> ArchitecturalSpec:
    """UNCONFIRMED placeholder response shape — see module docstring: `{"output" | "generated_text" |
    "text": "<generated text>"}`. Tries each key in order since different inference-server frameworks
    conventionally use different ones; whichever real key the actual model uses, update this one spot."""
    raw_text = response_body.get("output") or response_body.get("generated_text") or response_body.get("text")
    if not raw_text or not raw_text.strip():
        raise ArchitectModelEmptyResponseError("Architect Model returned an empty response")

    json_text = _extract_json_text(raw_text)
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as error:
        raise ArchitectModelMalformedJSONError(f"Architect Model output was not valid JSON: {error}") from error

    try:
        return ArchitecturalSpec.model_validate(parsed)
    except ValidationError as error:
        raise ArchitectModelInvalidOutputError(
            f"Architect Model output did not match the ArchitecturalSpec contract: {error}"
        ) from error


class RealArchitectModelGateway(ArchitectModelGateway):
    def __init__(self, config: RealArchitectModelConfig, client: httpx.Client | None = None) -> None:
        self._config = config
        # A caller-supplied client (tests) bypasses real network I/O entirely — see
        # backend/tests/test_real_gateway.py, which uses httpx's MockTransport for this.
        self._client = client or httpx.Client(timeout=config.timeout_s)

    def generate(self, request: ArchitectModelRequest) -> ArchitecturalSpec:
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"

        payload = _build_payload(request, self._config.model_id)

        try:
            response = self._client.post(self._config.base_url, json=payload, headers=headers)
        except httpx.TimeoutException as error:
            raise ArchitectModelTimeoutError(f"Architect Model inference timed out: {error}") from error
        except httpx.HTTPError as error:
            raise ArchitectModelUnavailableError(
                f"Architect Model inference endpoint unreachable: {error}"
            ) from error

        if response.status_code >= 500:
            raise ArchitectModelUnavailableError(
                f"Architect Model inference endpoint returned {response.status_code}"
            )
        if response.status_code >= 400:
            raise ArchitectModelInvalidOutputError(
                f"Architect Model inference endpoint rejected the request ({response.status_code})"
            )

        try:
            body = response.json()
        except ValueError as error:
            raise ArchitectModelMalformedJSONError(f"Architect Model response was not valid JSON: {error}") from error

        return _extract_architectural_spec(body)
