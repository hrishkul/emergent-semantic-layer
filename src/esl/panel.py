"""LangGraph debate: five verticals, then a critique, then a judge.

Round 1 calls do not read each other. Round 2 critiques the same verbatim
claim list. The summarizer's digest is for the judge and the reviewer.
Short-term state dies with the run. Tools read the profile, the warehouse,
and the document index. No checkpoint, no memory of a previous debate.

    python -m esl.panel
"""

import json
import os
import re
import threading
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from esl.debate import CHOSEN_MODEL_ID, VERTICALS, DebateSpec, parse_debate_spec
from esl.llm import (
    BudgetExceeded,
    Completion,
    GemmaClient,
    Ledger,
    ToolCall,
    parse_gemma_tool_calls,
)
from esl.ontology import DOC_SHEETS, FOUNDATION_NODES

SPEC_PATH = Path(__file__).resolve().parents[2] / "specs" / "ontology_debate.json"
_TABLE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_MAX_TOOL_TURNS = 2
ONTOLOGY_SHAPE = """{
  "schema_version": 1,
  "name": "erp-mtdd",
  "slice": "sales",
  "shared_foundation": true,
  "nodes": [{
    "id": "customer",
    "name": "short name",
    "description": "what this node means, including cited dissent",
    "grain": "one row per ...",
    "tables": [{"name": "bronze_slug", "source_name": "Workbook Table", "role": "authoritative"}],
    "documents": [{"sheet": "Column Dictionary", "locator": "Table.Column"}]
  }],
  "edges": [{
    "id": "order_customer",
    "source": "order",
    "target": "customer",
    "name": "placed_by",
    "description": "why this foreign key exists",
    "column": "Foreign_Key_Column",
    "documents": [{"sheet": "Relationships", "locator": "child table and column"}]
  }]
}"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Search the schema workbook. Returns passages with sheet and locator.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "profile_summary",
            "description": "Bronze profile summary: rows, key failures, relationship failures.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "profile_table",
            "description": "Profile of one documented table: rows, primary key, column drift.",
            "parameters": {
                "type": "object",
                "properties": {"table": {"type": "string"}},
                "required": ["table"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sample_rows",
            "description": "Return up to 3 rows from one bronze table. Pass the bronze table name.",
            "parameters": {
                "type": "object",
                "properties": {"table": {"type": "string"}},
                "required": ["table"],
            },
        },
    },
]


def _merge_map(left: dict, right: dict) -> dict:
    merged = dict(left)
    merged.update(right)
    return merged


class DebateState(TypedDict):
    claims: Annotated[dict, _merge_map]
    critiques: Annotated[dict, _merge_map]
    claim_list: str
    digest: str
    proposal: str


@dataclass
class ToolBox:
    search: Callable[[str], str]
    profile: dict | None
    sample: Callable[[str], str]

    def call(self, name: str, arguments: dict) -> str:
        try:
            if name == "search_documents":
                return self.search(str(arguments.get("query") or ""))
            if name == "profile_summary":
                return _profile_summary(self.profile)
            if name == "profile_table":
                return _profile_table(self.profile, str(arguments.get("table") or ""))
            if name == "sample_rows":
                return self.sample(str(arguments.get("table") or ""))
            return f"unknown tool {name}"
        except Exception as exc:
            return f"tool failed: {exc}"


def react(
    client, messages: list[dict], tools: ToolBox, max_tokens: int, *, require_tool: bool = False
) -> str:
    """A few tool calls, then a final answer. The message list is this call only."""

    thread = [dict(message) for message in messages]
    for turn in range(_MAX_TOOL_TURNS):
        completion = client.complete(
            thread,
            tools=TOOLS,
            max_tokens=max_tokens,
            tool_choice="required" if require_tool and turn == 0 else "auto",
        )
        calls = _resolved_calls(completion)
        if not calls:
            return _answer(client, thread, completion, max_tokens)
        thread.append(_assistant_message(Completion("", calls)))
        for call in calls:
            thread.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": tools.call(call.name, call.arguments)[:8000],
                }
            )
    final = client.complete(thread, tools=None, max_tokens=max_tokens)
    return _answer(client, thread, final, max_tokens)


def build_graph(client, tools: ToolBox, spec: DebateSpec):
    stances = {debater.id: debater for debater in spec.participants.debaters}

    def claim(vertical: str):
        def node(state: DebateState) -> dict:
            _say(f"claim {vertical}")
            debater = stances[vertical]
            text = _speak(
                client,
                tools,
                _claim_messages(debater.id, debater.background, debater.stance),
                max_tokens=1800,
                require_tool=True,
            )
            return {"claims": {vertical: text}}

        return node

    def assemble(state: DebateState) -> dict:
        lines = []
        number = 0
        for vertical in VERTICALS:
            for claim in _claim_lines(state["claims"].get(vertical, "")):
                lines.append(f"[{number}] {vertical}\n{claim}")
                number += 1
        return {"claim_list": "\n\n".join(lines)}

    def critique(vertical: str):
        def node(state: DebateState) -> dict:
            _say(f"critique {vertical}")
            debater = stances[vertical]
            text = _speak(
                client,
                tools,
                _critique_messages(
                    debater.id, debater.background, debater.stance, state["claim_list"]
                ),
                max_tokens=1800,
                require_tool=True,
            )
            return {"critiques": {vertical: text}}

        return node

    def summarize(state: DebateState) -> dict:
        _say("summarize")
        text = _speak(
            client,
            tools,
            [
                {
                    "role": "system",
                    "content": (
                        "Write a short digest of these verbatim claims for a human reviewer. "
                        "Do not drop a claim. Do not decide the ontology."
                    ),
                },
                {"role": "user", "content": state["claim_list"]},
            ],
            max_tokens=700,
        )
        return {"digest": text}

    def judge(state: DebateState) -> dict:
        _say("judge")
        critiques = "\n\n".join(
            f"{vertical}\n{state['critiques'].get(vertical, '')}" for vertical in VERTICALS
        )
        text = _speak(
            client,
            tools,
            _judge_messages(state["claim_list"], critiques, state["digest"]),
            max_tokens=4096,
        )
        return {"proposal": text}

    graph = StateGraph(DebateState)
    for vertical in VERTICALS:
        graph.add_node(f"claim_{vertical}", claim(vertical))
        graph.add_edge(START, f"claim_{vertical}")
        graph.add_edge(f"claim_{vertical}", "assemble")
    graph.add_node("assemble", assemble)
    for vertical in VERTICALS:
        graph.add_node(f"critique_{vertical}", critique(vertical))
        graph.add_edge("assemble", f"critique_{vertical}")
        graph.add_edge(f"critique_{vertical}", "summarize")
    graph.add_node("summarize", summarize)
    graph.add_node("judge", judge)
    graph.add_edge("summarize", "judge")
    graph.add_edge("judge", END)
    return graph.compile()


def run_debate(client, tools: ToolBox, spec: DebateSpec | None = None) -> dict:
    spec = spec or parse_debate_spec(SPEC_PATH.read_bytes())
    app = build_graph(client, tools, spec)
    state = app.invoke(
        {"claims": {}, "critiques": {}, "claim_list": "", "digest": "", "proposal": ""}
    )
    proposal, errors = _ontology_from_judge(client, state["proposal"])
    return {
        "model": CHOSEN_MODEL_ID,
        "claims": {vertical: state["claims"].get(vertical, "") for vertical in VERTICALS},
        "critiques": {vertical: state["critiques"].get(vertical, "") for vertical in VERTICALS},
        "claim_list": state["claim_list"],
        "digest": state["digest"],
        "proposal_text": state["proposal"],
        "proposal": proposal,
        "proposal_errors": errors,
    }


def _ontology_from_judge(client, text: str) -> tuple[dict | None, list[str]]:
    from esl.ontology import parse_ontology
    from esl.schema import SchemaError

    errors: list[str] = []
    for attempt in (text, None):
        raw = attempt
        if raw is None:
            raw = _complete_text(
                client,
                [
                    {
                        "role": "system",
                        "content": (
                            "The previous ontology JSON was rejected. "
                            "Return one corrected JSON object and nothing else. "
                            "No markdown. No extra fields.\n"
                            f"Shape:\n{ONTOLOGY_SHAPE}\n"
                            "Errors: " + "; ".join(errors)
                        ),
                    },
                    {"role": "user", "content": text[:6000]},
                ],
                max_tokens=4096,
            )
        try:
            payload = json.loads(_json_object(raw))
            ontology = parse_ontology(json.dumps(payload).encode())
            return ontology.model_dump(mode="json"), []
        except (json.JSONDecodeError, SchemaError, ValueError) as exc:
            detail = exc.errors if isinstance(exc, SchemaError) else [str(exc)]
            errors = detail
    return None, errors


def _complete_text(client, messages: list[dict], max_tokens: int) -> str:
    try:
        return client.complete(messages, tools=None, max_tokens=max_tokens).content
    except BudgetExceeded as exc:
        return f"stopped: {exc}"
    except RuntimeError as exc:
        return f"error: {exc}"


def _speak(
    client, tools: ToolBox, messages: list[dict], max_tokens: int, *, require_tool: bool = False
) -> str:
    try:
        return react(client, messages, tools, max_tokens, require_tool=require_tool)
    except BudgetExceeded as exc:
        return f"stopped: {exc}"
    except RuntimeError as exc:
        return f"error: {exc}"


def _say(message: str) -> None:
    if os.environ.get("ESL_DEBATE_QUIET") != "1":
        print(message, flush=True)


def _claim_messages(vertical: str, background: str, stance: str) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                f"You are the {vertical} vertical in a cross-vertical ontology debate.\n"
                f"Background: {background}\n"
                f"Stance: {stance}\n"
                "You cannot see the other verticals. Argue only this stance.\n"
                "Call search_documents and profile_summary before you write. "
                "Do not write a tool call in the answer.\n"
                "Write one claim for each fact your stance depends on. Cover the shared "
                "concepts you touch: customer, item, legal entity, order, invoice, stock. "
                "Each claim cites a sheet and locator, or a bronze table, that a tool returned. "
                "Copy those names. Do not invent a table.\n"
                'Then reply with JSON only: {"claims":[{"text":"...","citations":'
                '[{"sheet":"...","locator":"..."}]}]}'
            ),
        },
        {"role": "user", "content": "State your claims."},
    ]


def _critique_messages(vertical: str, background: str, stance: str, claim_list: str) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                f"You are the {vertical} vertical.\n"
                f"Background: {background}\n"
                f"Stance: {stance}\n"
                "Critique the verbatim claim list. You do not see the other critiques.\n"
                "Write one critique for every numbered claim. Contest a claim that "
                "contradicts your stance. Support a claim only when your stance agrees. "
                "When you can cite a fact the claim does not answer, say it is unanswered.\n"
                "Use tools when the list has no citation for your point.\n"
                'Reply with JSON only: {"critiques":[{"claim":0,"position":"support",'
                '"text":"...","citations":[{"sheet":"...","locator":"..."}]}]}'
            ),
        },
        {"role": "user", "content": "Critique the claim list.\n\n" + claim_list},
    ]


def _judge_messages(claim_list: str, critiques: str, digest: str) -> list[dict]:
    sheets = ", ".join(DOC_SHEETS)
    nodes = ", ".join(FOUNDATION_NODES)
    return [
        {
            "role": "system",
            "content": (
                "You are the judge. You write one ontology proposal. You do not approve it.\n"
                "Evaluate the arguments. Keep a cited claim that another vertical did not answer, "
                "and say which claim in the node or edge description.\n"
                "Use only tables and document locators that appear in the claims or critiques.\n"
                f"Required node ids: {nodes}.\n"
                "Each node has exactly one authoritative table and at least one document link. "
                "A second table may be role duplicate.\n"
                "Each edge's source holds the foreign-key column. source and target are node ids.\n"
                f"Document sheets: {sheets}.\n"
                'schema_version is 1. name is "erp-mtdd". slice is "sales". '
                "shared_foundation is true.\n"
                "Table name is the bronze slug from the claims. source_name is the workbook "
                "table name from the claims. Do not invent either.\n"
                "The shape lists the fields. It is not a limit on how many nodes or edges. "
                "Write one edge for every foreign key the claims or critiques name. "
                "Keep cited dissent in the description of the node it concerns.\n"
                "Extra fields are rejected. Reply with one JSON object and nothing else.\n"
                f"Shape:\n{ONTOLOGY_SHAPE}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"CLAIMS\n{claim_list}\n\nCRITIQUES\n{critiques}\n\nDIGEST\n{digest}"
            ),
        },
    ]


def _resolved_calls(completion: Completion) -> list[ToolCall]:
    if completion.tool_calls:
        return completion.tool_calls
    return parse_gemma_tool_calls(completion.content)


def _answer(client, thread: list[dict], completion: Completion, max_tokens: int) -> str:
    if "<|tool_call>" not in (completion.content or ""):
        return completion.content
    thread.append({"role": "assistant", "content": completion.content})
    thread.append(
        {"role": "user", "content": "Stop calling tools. Reply with the JSON answer only."}
    )
    repaired = client.complete(thread, tools=None, max_tokens=max_tokens)
    return repaired.content


def _assistant_message(completion: Completion) -> dict:
    return {
        "role": "assistant",
        "content": completion.content,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in completion.tool_calls
        ],
    }


def _json_object(text: str) -> str:
    body = text.strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:json)?", "", body).strip()
        body = re.sub(r"```$", "", body).strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("model reply has no JSON object")
    return body[start : end + 1]


def _claim_lines(raw: str) -> list[str]:
    try:
        payload = json.loads(_json_object(raw))
    except (json.JSONDecodeError, ValueError):
        return [raw.strip()] if raw.strip() else []
    claims = payload.get("claims") if isinstance(payload, dict) else None
    if not isinstance(claims, list) or not claims:
        return [raw.strip()] if raw.strip() else []
    lines = []
    for claim in claims:
        if not isinstance(claim, dict) or not claim.get("text"):
            lines.append(str(claim))
            continue
        cites = []
        for citation in claim.get("citations") or []:
            if isinstance(citation, dict):
                cites.append(f"{citation.get('sheet', '')} / {citation.get('locator', '')}")
        suffix = f"\nCited: {'; '.join(cites)}" if cites else ""
        lines.append(str(claim["text"]) + suffix)
    return lines


def _profile_summary(profile: dict | None) -> str:
    if not profile:
        return "profile unavailable"
    summary = dict(profile.get("summary") or {})
    tables = [
        f"{entry.get('source_name')}={entry.get('table')}"
        for entry in profile.get("tables") or []
        if entry.get("source_name") and entry.get("table")
    ]
    summary["table_names"] = tables
    return json.dumps(summary)


def _profile_table(profile: dict | None, table: str) -> str:
    if not profile:
        return "profile unavailable"
    key = table.strip().lower()
    for entry in profile.get("tables") or []:
        names = {str(entry.get("source_name", "")).lower(), str(entry.get("table", "")).lower()}
        if key in names:
            kept = {
                "source_name": entry.get("source_name"),
                "table": entry.get("table"),
                "rows": entry.get("rows"),
                "primary_key": entry.get("primary_key"),
                "columns_missing_from_data": entry.get("columns_missing_from_data"),
                "columns_not_documented": entry.get("columns_not_documented"),
            }
            return json.dumps(kept)
    return f"no profile for {table}"


def sample_rows(table: str, project: str, dataset: str, location: str) -> str:
    if not _TABLE.match(table):
        return "refused: table name must be a bronze slug"
    from google.cloud import bigquery

    client = bigquery.Client(project=project)
    job = bigquery.QueryJobConfig(maximum_bytes_billed=10_000_000)
    sql = f"SELECT * FROM `{project}.{dataset}.{table}` LIMIT 3"
    try:
        rows = client.query(sql, job_config=job, location=location).result()
    except Exception as exc:
        return f"warehouse query failed: {exc}"
    preview = [dict(row.items()) for row in rows]
    return json.dumps(preview, default=str)[:4000]


_embed_lock = threading.Lock()


def search_documents(query: str, database_url: str) -> str:
    from esl.db import connect
    from esl.retrieval import CORPUS, FastEmbedder, search_passages

    with _embed_lock:
        if search_documents.embedder is None:
            search_documents.embedder = FastEmbedder()
        embedder = search_documents.embedder
        with connect(database_url) as conn:
            hits = search_passages(
                conn, corpus=CORPUS, query=query, embedder=embedder, limit=4
            )
    lines = [f"{hit['sheet']} / {hit['locator']}: {hit['text'][:400]}" for hit in hits]
    return "\n".join(lines) if lines else "no passages"


search_documents.embedder = None


def load_profile(api_url: str) -> dict | None:
    artifact_id = _approved_artifact(api_url, "source_profile")
    if artifact_id is None:
        return None
    url = f"{api_url}/artifacts/{artifact_id}/content"
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.loads(response.read().decode())


def _approved_artifact(api_url: str, kind: str) -> str | None:
    with urllib.request.urlopen(f"{api_url}/proposals?status=approved", timeout=30) as response:
        proposals = json.loads(response.read().decode())
    for proposal in proposals:
        artifact_id = proposal["artifact_id"]
        with urllib.request.urlopen(f"{api_url}/artifacts/{artifact_id}", timeout=30) as response:
            artifact = json.loads(response.read().decode())
        if artifact["kind"] == kind and artifact["logical_name"] == "erp-mtdd":
            return artifact_id
    return None


def live_tools() -> ToolBox:
    from esl.settings import Settings

    settings = Settings.from_env()
    project = os.environ.get("BQ_PROJECT", "")
    dataset = os.environ.get("BQ_DATASET", "bronze_erp_mtdd")
    location = os.environ.get("BQ_LOCATION", "us-central1")
    api_url = os.environ.get("ESL_API_URL", "").rstrip("/")
    profile = load_profile(api_url) if api_url else None

    def search(query: str) -> str:
        return search_documents(query, settings.database_url)

    def sample(table: str) -> str:
        if not project:
            return "warehouse unavailable"
        return sample_rows(table, project, dataset, location)

    return ToolBox(search=search, profile=profile, sample=sample)


def submit(transcript: dict, ledger: Ledger) -> None:
    from esl.control_plane import ControlPlane
    from esl.debate import CHOSEN_MODEL_ID, CHOSEN_PROVIDER

    api_url = os.environ.get("ESL_API_URL", "").rstrip("/")
    if not api_url:
        print("ESL_API_URL is unset; transcript was not submitted")
        return
    actor = os.environ.get("ESL_ACTOR") or "debate"
    plane = ControlPlane(api_url, actor, timeout=60)
    spec = json.loads(SPEC_PATH.read_text())
    spec["participants"]["model"]["provider"] = CHOSEN_PROVIDER
    spec["participants"]["model"]["model_id"] = CHOSEN_MODEL_ID
    spec_result = plane.propose(
        kind="debate_spec",
        name="ontology",
        content=spec,
        summary=f"Debate model is {CHOSEN_MODEL_ID}. The panel is unchanged.",
    )
    _print_submission("debate_spec", spec_result)
    body = {
        "schema_version": 1,
        "model": CHOSEN_MODEL_ID,
        "claims": transcript["claims"],
        "critiques": transcript["critiques"],
        "digest": transcript["digest"],
        "proposal": transcript["proposal"],
        "proposal_text": transcript["proposal_text"],
        "proposal_errors": transcript["proposal_errors"],
        "usage": {
            "prompt_tokens": ledger.prompt_tokens,
            "completion_tokens": ledger.completion_tokens,
            "usd": round(ledger.usd, 6),
            "seconds": round(ledger.seconds, 1),
        },
    }
    transcript_result = plane.propose(
        kind="debate_transcript",
        name="erp-mtdd",
        content=body,
        summary=(
            f"Ontology debate transcript. ${ledger.usd:.4f}, {ledger.seconds:.0f}s. "
            "A person decides the proposal."
        ),
    )
    _print_submission("debate_transcript", transcript_result)
    if transcript["proposal"] is not None:
        parent = _approved_artifact(api_url, "ontology")
        ontology_result = plane.propose(
            kind="ontology",
            name="erp-mtdd",
            content=transcript["proposal"],
            summary="Ontology proposed by the judge. The judge did not approve it.",
            parent_artifact_id=parent,
        )
        _print_submission("ontology", ontology_result)


def _print_submission(kind: str, result: dict) -> None:
    artifact = result["artifact"]
    proposal = result.get("proposal")
    if proposal is None:
        print(f"{kind} unchanged: version {artifact['version']}")
        return
    print(f"{kind} version {artifact['version']}: proposal {proposal['id']} {proposal['status']}")


def main() -> int:
    project = os.environ.get("BQ_PROJECT", "")
    if not project:
        print("BQ_PROJECT is required", flush=True)
        return 1
    spec = parse_debate_spec(SPEC_PATH.read_bytes())
    ledger = Ledger(max_usd=spec.budgets.max_usd, max_seconds=spec.budgets.max_seconds)
    client = GemmaClient(ledger, project=project)
    transcript = run_debate(client, live_tools(), spec)
    print(
        f"done ${ledger.usd:.4f} in {ledger.seconds:.0f}s "
        f"proposal_errors={transcript['proposal_errors']}",
        flush=True,
    )
    submit(transcript, ledger)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
