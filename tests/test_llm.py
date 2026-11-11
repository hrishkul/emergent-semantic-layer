import json
import os

import httpx
import pytest

from esl.llm import LLMClient, LLMError
from esl.settings import Settings


def settings(**kw) -> Settings:
    return Settings(database_url="x", llm_api_key="k", **kw)


def test_chat_sends_openai_request() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    client = LLMClient(settings(), transport=httpx.MockTransport(handler))
    assert client.chat([{"role": "user", "content": "hi"}]) == "ok"
    assert seen["url"].endswith("/v1/chat/completions")
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["model"] == "nvidia/nemotron-3-ultra-550b-a55b"


def test_chat_raises_on_error_and_empty() -> None:
    bad = httpx.MockTransport(lambda r: httpx.Response(404, text="nope"))
    with pytest.raises(LLMError):
        LLMClient(settings(), transport=bad).chat([])
    empty = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": None}}]})
    )
    with pytest.raises(LLMError):
        LLMClient(settings(), transport=empty).chat([])


@pytest.mark.skipif(not os.environ.get("NVIDIA_API_KEY"), reason="NVIDIA_API_KEY not set")
def test_live_nim_call() -> None:
    client = LLMClient(Settings.from_env())
    assert client.chat([{"role": "user", "content": "Reply with the word: ok"}], max_tokens=64)
