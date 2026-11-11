"""Chat client for an OpenAI-compatible endpoint (NVIDIA NIM by default)."""

import httpx

from esl.settings import Settings


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        headers = {"Content-Type": "application/json"}
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"
        self.model = settings.llm_model
        self._http = httpx.Client(
            base_url=settings.llm_base_url.rstrip("/"),
            headers=headers,
            timeout=120,
            transport=transport,
        )

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> str:
        response = self._http.post(
            "/chat/completions",
            json={
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        if response.status_code != 200:
            raise LLMError(f"{response.status_code}: {response.text[:300]}")
        content = response.json()["choices"][0]["message"].get("content")
        if not content:
            raise LLMError("empty completion; raise max_tokens for reasoning models")
        return content
