"""One OpenAI-compatible client for every debate role.

The model is Gemma 4 on Vertex AI MaaS. A run keeps its own token ledger and
stops at the debate budget. Nothing here is kept for the next run.
"""

import json
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from esl.debate import CHOSEN_MODEL_ID

# Published rate used only to enforce the debate cap.
INPUT_USD_PER_TOKEN = 0.15 / 1_000_000
OUTPUT_USD_PER_TOKEN = 0.60 / 1_000_000


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Completion:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class Ledger:
    max_usd: float = 8
    max_seconds: float = 900
    prompt_tokens: int = 0
    completion_tokens: int = 0
    started: float = field(default_factory=time.monotonic)

    @property
    def usd(self) -> float:
        return (
            self.prompt_tokens * INPUT_USD_PER_TOKEN
            + self.completion_tokens * OUTPUT_USD_PER_TOKEN
        )

    @property
    def seconds(self) -> float:
        return time.monotonic() - self.started

    def add(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.check()

    def check(self) -> None:
        if self.usd > self.max_usd:
            raise BudgetExceeded(f"debate cost ${self.usd:.4f} is over ${self.max_usd}")
        if self.seconds > self.max_seconds:
            raise BudgetExceeded(f"debate ran {self.seconds:.0f}s, over {self.max_seconds:.0f}s")


class GemmaClient:
    """Chat completions against the global Vertex OpenAI-compatible endpoint."""

    def __init__(self, ledger: Ledger, project: str, timeout: float = 120) -> None:
        self.ledger = ledger
        self.project = project
        self.timeout = timeout
        self._lock = threading.Lock()
        self._creds = None

    def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int = 1024,
        tool_choice: str | None = None,
    ) -> Completion:
        with self._lock:
            self.ledger.check()
            body: dict = {
                "model": CHOSEN_MODEL_ID,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0,
            }
            if tools:
                body["tools"] = tools
                if tool_choice:
                    body["tool_choice"] = tool_choice
            payload = self._post(body)
            usage = payload.get("usage") or {}
            message = payload["choices"][0]["message"]
            calls = [_tool_call(raw) for raw in message.get("tool_calls") or []]
            completion = Completion(
                content=message.get("content") or "",
                tool_calls=calls,
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
            )
            self.ledger.add(completion.prompt_tokens, completion.completion_tokens)
            return completion

    def _post(self, body: dict) -> dict:
        token = self._token()
        url = (
            "https://aiplatform.googleapis.com/v1/projects/"
            f"{self.project}/locations/global/endpoints/openapi/chat/completions"
        )
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode()[:500]
            raise RuntimeError(f"gemma {exc.code}: {detail}") from exc

    def _token(self) -> str:
        import google.auth
        from google.auth.transport.requests import Request

        if self._creds is None:
            creds, _project = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            self._creds = creds
        if not self._creds.valid:
            self._creds.refresh(Request())
        return self._creds.token


_GEMMA_CALL = re.compile(
    r"<\|tool_call>call:([A-Za-z_][A-Za-z0-9_]*)\{(.*?)\}<tool_call\|>",
    re.DOTALL,
)


def parse_gemma_tool_calls(text: str) -> list[ToolCall]:
    """Gemma sometimes writes the tool call in the message instead of tool_calls."""

    calls = []
    for index, match in enumerate(_GEMMA_CALL.finditer(text or "")):
        calls.append(
            ToolCall(
                id=f"gemma-{index}",
                name=match.group(1),
                arguments=_gemma_arguments(match.group(2)),
            )
        )
    return calls


def _gemma_arguments(raw: str) -> dict:
    cleaned = raw.replace('<|"|>', '"').strip()
    if cleaned.startswith("{"):
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    found = dict(re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*:\s*"([^"]*)"', cleaned))
    return found


def _tool_call(raw: dict) -> ToolCall:
    function = raw.get("function") or {}
    arguments = function.get("arguments") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            arguments = {"_raw": arguments}
    if not isinstance(arguments, dict):
        arguments = {"_raw": arguments}
    return ToolCall(
        id=str(raw.get("id") or "call"),
        name=str(function.get("name") or ""),
        arguments=arguments,
    )
