"""Tests for provider selection: `app/architect/config.py`'s env parsing and
`app/architect/gateway.py::get_architect_model_gateway`'s mock/local/remote dispatch.
"""

import pytest

from app.architect.config import local_config_from_env, provider_name_from_env, real_config_from_env
from app.architect.gateway import MockArchitectModelGateway, get_architect_model_gateway


def test_provider_defaults_to_mock(monkeypatch):
    monkeypatch.delenv("ARCHITECT_MODEL_PROVIDER", raising=False)
    assert provider_name_from_env() == "mock"


def test_provider_name_is_lowercased_and_stripped(monkeypatch):
    monkeypatch.setenv("ARCHITECT_MODEL_PROVIDER", "  LOCAL  ")
    assert provider_name_from_env() == "local"


def test_get_gateway_mock(monkeypatch):
    monkeypatch.setenv("ARCHITECT_MODEL_PROVIDER", "mock")
    assert isinstance(get_architect_model_gateway(), MockArchitectModelGateway)


def test_get_gateway_unknown_provider_raises(monkeypatch):
    monkeypatch.setenv("ARCHITECT_MODEL_PROVIDER", "nonsense")
    with pytest.raises(RuntimeError, match="Unknown ARCHITECT_MODEL_PROVIDER"):
        get_architect_model_gateway()


def test_real_config_requires_base_url(monkeypatch):
    monkeypatch.delenv("ARCHITECT_MODEL_BASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="ARCHITECT_MODEL_BASE_URL"):
        real_config_from_env()


def test_local_config_requires_adapter_path(monkeypatch):
    monkeypatch.delenv("ARCHITECT_MODEL_ADAPTER_PATH", raising=False)
    with pytest.raises(RuntimeError, match="ARCHITECT_MODEL_ADAPTER_PATH"):
        local_config_from_env()


def test_local_config_defaults(monkeypatch):
    monkeypatch.setenv("ARCHITECT_MODEL_ADAPTER_PATH", "/some/path")
    monkeypatch.delenv("ARCHITECT_MODEL_BASE_MODEL_ID", raising=False)
    monkeypatch.delenv("ARCHITECT_MODEL_MAX_NEW_TOKENS", raising=False)

    config = local_config_from_env()

    assert config.base_model_id == "Qwen/Qwen2.5-Coder-7B-Instruct"
    assert config.adapter_path == "/some/path"
    assert config.max_new_tokens == 2048


def test_get_gateway_local_requires_adapter_path_before_touching_torch(monkeypatch):
    # provider=local but no adapter path -> must fail on config validation, before any attempt to
    # import torch/transformers/peft or load the 7B model.
    monkeypatch.setenv("ARCHITECT_MODEL_PROVIDER", "local")
    monkeypatch.delenv("ARCHITECT_MODEL_ADAPTER_PATH", raising=False)

    with pytest.raises(RuntimeError, match="ARCHITECT_MODEL_ADAPTER_PATH"):
        get_architect_model_gateway()
