"""Runtime configuration for selecting and configuring an `ArchitectModelGateway` provider — read from
environment variables only; nothing here is hardcoded or committed to source control.

ARCHITECT_MODEL_PROVIDER=mock|local|remote   (default: "mock")

mock:   MockArchitectModelGateway — deterministic, in-repo, no model involved.
local:  LocalArchitectModelGateway — loads Qwen2.5-Coder-7B-Instruct + the accepted LoRA adapter
        in-process via transformers/peft. Only these settings apply, and only this provider ever
        loads the 7B model:

ARCHITECT_MODEL_BASE_MODEL_ID   — HF base model id (default: "Qwen/Qwen2.5-Coder-7B-Instruct")
ARCHITECT_MODEL_ADAPTER_PATH    — path to the LoRA adapter (REQUIRED for provider=local)
ARCHITECT_MODEL_MAX_NEW_TOKENS  — generation budget (default: 2048, matches the verified eval script)

remote: RealArchitectModelGateway — calls an external HTTP inference endpoint. Kept for a future
        deployed serving layer; its wire protocol is still an unconfirmed placeholder (see
        `app/architect/real_gateway.py`'s module docstring) — unlike `local`, which reproduces a
        verified real contract. Only these settings apply:

ARCHITECT_MODEL_BASE_URL     — inference endpoint URL (REQUIRED for provider=remote)
ARCHITECT_MODEL_ID           — model identifier to request, if the endpoint serves multiple (optional)
ARCHITECT_MODEL_API_KEY      — bearer token for the inference endpoint (optional; never logged)
ARCHITECT_MODEL_TIMEOUT_S    — request timeout in seconds (default: 30)

See `backend/.env.example` for a template.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RealArchitectModelConfig:
    base_url: str
    model_id: str | None
    api_key: str | None
    timeout_s: float


@dataclass(frozen=True)
class LocalArchitectModelConfig:
    base_model_id: str
    adapter_path: str
    max_new_tokens: int


def provider_name_from_env() -> str:
    return os.environ.get("ARCHITECT_MODEL_PROVIDER", "mock").strip().lower()


def real_config_from_env() -> RealArchitectModelConfig:
    base_url = os.environ.get("ARCHITECT_MODEL_BASE_URL")
    if not base_url:
        raise RuntimeError("ARCHITECT_MODEL_PROVIDER=remote requires ARCHITECT_MODEL_BASE_URL to be set")

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


def local_config_from_env() -> LocalArchitectModelConfig:
    adapter_path = os.environ.get("ARCHITECT_MODEL_ADAPTER_PATH")
    if not adapter_path:
        raise RuntimeError("ARCHITECT_MODEL_PROVIDER=local requires ARCHITECT_MODEL_ADAPTER_PATH to be set")

    max_new_tokens_raw = os.environ.get("ARCHITECT_MODEL_MAX_NEW_TOKENS", "2048")
    try:
        max_new_tokens = int(max_new_tokens_raw)
    except ValueError:
        raise RuntimeError(f"ARCHITECT_MODEL_MAX_NEW_TOKENS must be an integer, got {max_new_tokens_raw!r}") from None

    return LocalArchitectModelConfig(
        base_model_id=os.environ.get("ARCHITECT_MODEL_BASE_MODEL_ID", "Qwen/Qwen2.5-Coder-7B-Instruct"),
        adapter_path=adapter_path,
        max_new_tokens=max_new_tokens,
    )
