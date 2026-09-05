"""Runtime configuration for selecting and configuring an `ArchitectModelGateway` provider — read from
environment variables only; nothing here is hardcoded or committed to source control.

ARCHITECT_MODEL_PROVIDER=mock|real   (default: "mock")

When `real`, these additionally apply:

ARCHITECT_MODEL_BASE_URL     — inference endpoint URL (REQUIRED for provider=real)
ARCHITECT_MODEL_ID           — model identifier to request, if the endpoint serves multiple (optional)
ARCHITECT_MODEL_API_KEY      — bearer token for the inference endpoint (optional; never logged)
ARCHITECT_MODEL_TIMEOUT_S    — request timeout in seconds (default: 30)

See `backend/.env.example` for a template. See `app/architect/real_gateway.py`'s module docstring for
why the actual wire protocol these settings configure is an unconfirmed placeholder.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RealArchitectModelConfig:
    base_url: str
    model_id: str | None
    api_key: str | None
    timeout_s: float


def provider_name_from_env() -> str:
    return os.environ.get("ARCHITECT_MODEL_PROVIDER", "mock").strip().lower()


def real_config_from_env() -> RealArchitectModelConfig:
    base_url = os.environ.get("ARCHITECT_MODEL_BASE_URL")
    if not base_url:
        raise RuntimeError("ARCHITECT_MODEL_PROVIDER=real requires ARCHITECT_MODEL_BASE_URL to be set")

    timeout_raw = os.environ.get("ARCHITECT_MODEL_TIMEOUT_S", "30")
    try:
        timeout_s = float(timeout_raw)
    except ValueError:
        raise RuntimeError(f"ARCHITECT_MODEL_TIMEOUT_S must be a number, got {timeout_raw!r}") from None

    return RealArchitectModelConfig(
        base_url=base_url,
        model_id=os.environ.get("ARCHITECT_MODEL_ID") or None,
        api_key=os.environ.get("ARCHITECT_MODEL_API_KEY") or None,
        timeout_s=timeout_s,
    )
