"""Typed failure classes for calling an external Architect Model. Each carries a `code` used both for
backend diagnostics/logging (see `app/design/pipeline.py`) and for the API's structured error response
(see `app/design/router.py`) — the frontend switches on `code` to show a specific, understandable
message instead of collapsing everything into one generic "design generation failed" string (see
`frontend/src/api.ts`).

These are deliberately separate exception TYPES (not one exception with a status field) so a caller can
`except` the specific failure it cares about — e.g. retry logic could reasonably retry
`ArchitectModelTimeoutError` but never `ArchitectModelInvalidOutputError`. All inherit from
`ArchitectModelError` for callers that just want to catch "any gateway failure."
"""


class ArchitectModelError(Exception):
    """Base class for every Architect Model gateway failure."""

    code = "ARCHITECT_MODEL_INVALID_OUTPUT"  # safe fallback: "got a response, couldn't use it"


class ArchitectModelUnavailableError(ArchitectModelError):
    """The inference provider could not be reached at all — connection refused, DNS failure, or a
    5xx from the provider itself. Distinct from a timeout (the provider never even responded) and
    from invalid output (the provider responded but with something unusable)."""

    code = "ARCHITECT_MODEL_UNAVAILABLE"


class ArchitectModelTimeoutError(ArchitectModelError):
    """The inference call did not complete within the configured timeout."""

    code = "ARCHITECT_MODEL_TIMEOUT"


class ArchitectModelEmptyResponseError(ArchitectModelError):
    """The provider responded successfully (2xx) but returned no usable text at all."""

    code = "ARCHITECT_MODEL_INVALID_OUTPUT"


class ArchitectModelMalformedJSONError(ArchitectModelError):
    """The model's text response could not be parsed as JSON at all (not the same as valid JSON that
    fails schema validation — see `ArchitectModelInvalidOutputError`)."""

    code = "ARCHITECT_MODEL_INVALID_OUTPUT"


class ArchitectModelInvalidOutputError(ArchitectModelError):
    """The model's response was valid JSON but failed `ArchitecturalSpec` validation — this is also
    where an unsupported room/constraint `kind` value ends up: `ArchitecturalSpec.relationships`'
    discriminated union rejects any `kind` it doesn't recognize as a normal Pydantic validation
    failure, which is exactly the "model produced an unsupported constraint type" case."""

    code = "ARCHITECT_MODEL_INVALID_OUTPUT"
