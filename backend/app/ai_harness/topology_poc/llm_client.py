"""A minimal, self-contained Ollama HTTP client for this POC — deliberately NOT a dependency on
`tests.ai_harness`'s provider factory (that package is a TEST-time harness for production AI
features; this POC is research code and must not create an inverted app->tests import). Every
config point is an env var, matching this repo's existing convention (`OLLAMA_BASE_URL`,
`tests/ai_harness/config.py`).

`TOPOLOGY_POC_MODEL` (default: `llama3.2:latest`, the only generally-reliable local model reachable
from this sandbox — no external network egress / API key is available here; see the results report
for the honest disclosure this implies about ceiling quality).
"""
from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass

DEFAULT_MODEL = os.environ.get("TOPOLOGY_POC_MODEL", "llama3.2:latest")
DEFAULT_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_TIMEOUT_S = float(os.environ.get("TOPOLOGY_POC_TIMEOUT_S", "180"))


@dataclass(frozen=True)
class LLMCallResult:
    text: str
    latency_s: float
    model: str


class LLMClientError(RuntimeError):
    """Raised on a transport/HTTP failure — never caught and hidden by the runner."""


def generate(prompt: str, *, system_prompt: str = "", model: str = DEFAULT_MODEL,
            base_url: str = DEFAULT_BASE_URL, num_predict: int = 3500, temperature: float = 0.6,
            timeout_s: float = DEFAULT_TIMEOUT_S) -> LLMCallResult:
    import time

    full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    payload = json.dumps({
        "model": model, "prompt": full_prompt, "stream": False,
        "options": {"num_predict": num_predict, "temperature": temperature},
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/api/generate", data=payload, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            data = json.loads(response.read())
    except Exception as exc:  # noqa: BLE001 - re-raised as this module's own error type
        raise LLMClientError(f"Ollama call to {base_url} failed: {type(exc).__name__}: {exc}") from exc
    latency = time.time() - t0
    return LLMCallResult(text=data.get("response", ""), latency_s=latency, model=model)
