"""LLM response cache — JSON files keyed by exactly
sha256(provider + model + prompt_version + system_prompt + input + relevant_config),
as specified. Avoids paying for/re-running identical semantic test calls."""

from __future__ import annotations

import hashlib
import json
import os

_DEFAULT_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")


def _key(provider: str, model: str, prompt_version: str, system_prompt: str, input_text: str,
         config: dict) -> str:
    payload = json.dumps({
        "provider": provider, "model": model, "prompt_version": prompt_version,
        "system_prompt": system_prompt, "input": input_text, "config": config,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ResponseCache:
    def __init__(self, cache_dir: str | None = None):
        self.cache_dir = cache_dir or _DEFAULT_CACHE_DIR
        os.makedirs(self.cache_dir, exist_ok=True)
        self.hits = 0
        self.misses = 0

    def get(self, *, provider: str, model: str, prompt_version: str, system_prompt: str,
            input_text: str, config: dict | None = None) -> dict | None:
        path = self._path(provider, model, prompt_version, system_prompt, input_text, config or {})
        if os.path.exists(path):
            self.hits += 1
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        self.misses += 1
        return None

    def set(self, *, provider: str, model: str, prompt_version: str, system_prompt: str,
            input_text: str, response: dict, config: dict | None = None) -> None:
        path = self._path(provider, model, prompt_version, system_prompt, input_text, config or {})
        with open(path, "w", encoding="utf-8") as f:
            json.dump(response, f)

    def _path(self, provider, model, prompt_version, system_prompt, input_text, config) -> str:
        key = _key(provider, model, prompt_version, system_prompt, input_text, config)
        return os.path.join(self.cache_dir, f"{key}.json")

    def clear(self) -> None:
        for name in os.listdir(self.cache_dir):
            if name.endswith(".json"):
                os.remove(os.path.join(self.cache_dir, name))

    def stats(self) -> dict:
        return {"hits": self.hits, "misses": self.misses}
