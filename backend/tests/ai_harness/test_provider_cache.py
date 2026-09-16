from tests.ai_harness.cache import ResponseCache
from tests.ai_harness.providers.mock_provider import MockTestLLMProvider


def test_mock_provider_is_deterministic():
    provider = MockTestLLMProvider()
    a = provider.complete("hello", system_prompt="sys")
    b = provider.complete("hello", system_prompt="sys")
    assert a.text == b.text
    c = provider.complete("different", system_prompt="sys")
    assert c.text != a.text


def test_cache_miss_then_hit(tmp_path):
    cache = ResponseCache(cache_dir=str(tmp_path))
    key_kwargs = dict(provider="mock", model="mock-v1", prompt_version="v1", system_prompt="sys", input_text="hello")

    assert cache.get(**key_kwargs) is None
    cache.set(**key_kwargs, response={"text": "cached-answer"})
    assert cache.get(**key_kwargs) == {"text": "cached-answer"}
    assert cache.stats() == {"hits": 1, "misses": 1}


def test_changing_model_invalidates_cache(tmp_path):
    cache = ResponseCache(cache_dir=str(tmp_path))
    cache.set(provider="mock", model="model-a", prompt_version="v1", system_prompt="", input_text="x",
              response={"text": "a"})
    assert cache.get(provider="mock", model="model-b", prompt_version="v1", system_prompt="", input_text="x") is None


def test_changing_prompt_version_invalidates_cache(tmp_path):
    cache = ResponseCache(cache_dir=str(tmp_path))
    cache.set(provider="mock", model="m", prompt_version="v1", system_prompt="", input_text="x",
              response={"text": "a"})
    assert cache.get(provider="mock", model="m", prompt_version="v2", system_prompt="", input_text="x") is None


def test_explicit_clear_invalidates_all(tmp_path):
    cache = ResponseCache(cache_dir=str(tmp_path))
    cache.set(provider="mock", model="m", prompt_version="v1", system_prompt="", input_text="x", response={"text": "a"})
    cache.clear()
    assert cache.get(provider="mock", model="m", prompt_version="v1", system_prompt="", input_text="x") is None
