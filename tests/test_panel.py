import json
import os

import pytest

from esl.debate import VERTICALS, parse_debate_spec
from esl.llm import Completion, Ledger, ToolCall, parse_gemma_tool_calls
from esl.panel import SPEC_PATH, ToolBox, react, run_debate, sample_rows

os.environ["ESL_DEBATE_QUIET"] = "1"


class Scripted:
    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    def complete(self, messages, tools=None, max_tokens=1024, tool_choice=None):
        self.calls.append(messages)
        system = messages[0]["content"]
        user = messages[-1]["content"]
        if "Write a short digest" in system:
            return Completion("digest of the claims")
        if "You are the judge" in system or "previous ontology JSON" in system:
            return Completion('{"schema_version": 1}')
        vertical = next(name for name in VERTICALS if f"You are the {name} vertical" in system)
        if "verbatim claim list" in system:
            return Completion(f"critique-from-{vertical}")
        if "State your claims" in user:
            return Completion(f"claim-from-{vertical}")
        return Completion("unused")


def test_round_one_does_not_read_the_other_verticals() -> None:
    client = Scripted()
    tools = ToolBox(search=lambda _q: "", profile=None, sample=lambda _t: "")
    spec = parse_debate_spec(SPEC_PATH.read_bytes())
    result = run_debate(client, tools, spec)
    claim_calls = [call for call in client.calls if "State your claims" in call[-1]["content"]]
    assert len(claim_calls) == 5
    for call in claim_calls:
        blob = json.dumps(call)
        assert "claim-from-" not in blob
        assert "External revenue exists when it is invoiced" not in blob or (
            "You are the finance vertical" in call[0]["content"]
        )
    sales = next(call for call in claim_calls if "You are the sales vertical" in call[0]["content"])
    assert "External revenue exists when it is invoiced" not in json.dumps(sales)
    critique = next(
        call for call in client.calls if "verbatim claim list" in call[0]["content"]
    )
    for vertical in VERTICALS:
        assert f"claim-from-{vertical}" in critique[-1]["content"]
    judge = next(call for call in client.calls if "You are the judge" in call[0]["content"])
    assert "bronze_slug" in judge[0]["content"]
    assert "Mastered in Sales" not in judge[0]["content"]
    assert "critique-from-sales" in judge[-1]["content"]
    assert "digest of the claims" in judge[-1]["content"]
    assert result["proposal"] is None
    assert result["proposal_errors"]
    assert result["claims"]["inventory"].startswith("claim-from-inventory")


def test_react_passes_the_tool_result_back() -> None:
    seen: list[list[dict]] = []

    class TwoTurn:
        def __init__(self) -> None:
            self.n = 0

        def complete(self, messages, tools=None, max_tokens=1024, tool_choice=None):
            seen.append(messages)
            self.n += 1
            if self.n == 1:
                return Completion("", [ToolCall("c1", "search_documents", {"query": "invoice"})])
            return Completion("cited the passage")

    tools = ToolBox(
        search=lambda query: f"Column Dictionary / Invoices.Customer_Invoice_ID for {query}",
        profile=None,
        sample=lambda _t: "",
    )
    text = react(TwoTurn(), [{"role": "user", "content": "State your claims."}], tools, 100)
    assert text == "cited the passage"
    assert "Invoices.Customer_Invoice_ID" in seen[1][-1]["content"]


def test_gemma_tool_markup_is_executed_before_the_claim() -> None:
    markup = (
        '<|tool_call>call:sample_rows{table:<|"|>companies<|"|>}<tool_call|>'
        '<|tool_call>call:sample_rows{table:<|"|>tax_codes<|"|>}<tool_call|>'
        '<|tool_call>call:sample_rows{table:<|"|>customers<|"|>}<tool_call|>'
    )
    calls = parse_gemma_tool_calls(markup)
    assert [call.arguments["table"] for call in calls] == [
        "companies",
        "tax_codes",
        "customers",
    ]
    sampled: list[str] = []

    class MarkupThenClaim:
        def __init__(self) -> None:
            self.n = 0

        def complete(self, messages, tools=None, max_tokens=1024, tool_choice=None):
            self.n += 1
            if self.n == 1:
                return Completion(markup)
            return Completion(
                '{"claims":[{"text":"External revenue is invoiced.","citations":[]}]}'
            )

    tools = ToolBox(
        search=lambda _q: "",
        profile=None,
        sample=lambda table: sampled.append(table) or f"rows from {table}",
    )
    text = react(
        MarkupThenClaim(),
        [{"role": "user", "content": "State your claims."}],
        tools,
        100,
        require_tool=True,
    )
    assert sampled == ["companies", "tax_codes", "customers"]
    assert "External revenue is invoiced." in text


def test_sample_rows_refuses_a_statement() -> None:
    assert sample_rows("sales_orders;drop", "p", "d", "us-central1").startswith("refused")


def test_ledger_stops_over_the_cap() -> None:
    ledger = Ledger(max_usd=0.0000001, max_seconds=900)
    with pytest.raises(Exception, match="debate cost"):
        ledger.add(prompt_tokens=100, completion_tokens=0)
