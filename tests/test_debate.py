import json
from pathlib import Path

import pytest

from esl.debate import DebateSpecError, parse_debate_spec

SPEC_PATH = Path(__file__).resolve().parents[1] / "specs" / "ontology_debate.json"


def test_checked_in_spec_matches_the_framework() -> None:
    spec = parse_debate_spec(SPEC_PATH.read_bytes())
    assert spec.name == "ontology"
    assert spec.scope == "cross_vertical"
    assert spec.materialization.slice == "sales"
    assert spec.materialization.shared_foundation is True
    assert [debater.id for debater in spec.participants.debaters] == [
        "sales",
        "finance",
        "inventory",
        "procurement",
        "production",
    ]
    assert spec.agreement.resolution == "argument_evaluation"
    assert spec.promotion.policy == "human_required"
    assert spec.participants.model.provider is None
    assert spec.participants.model.model_id is None


def test_majority_vote_is_rejected() -> None:
    payload = json.loads(SPEC_PATH.read_text())
    payload["agreement"]["resolution"] = "majority_vote"
    payload["interaction"]["structure"] = "fully_connected"
    with pytest.raises(DebateSpecError) as caught:
        parse_debate_spec(json.dumps(payload).encode())
    text = " ".join(caught.value.errors)
    assert "argument evaluation" in text
    assert "sparse" in text


def test_sales_only_panel_is_rejected() -> None:
    payload = json.loads(SPEC_PATH.read_text())
    payload["participants"]["debaters"] = [
        {
            "id": "sales",
            "background": "Orders",
            "stance": "Everything is a sale.",
        }
    ]
    with pytest.raises(DebateSpecError) as caught:
        parse_debate_spec(json.dumps(payload).encode())
    assert "five verticals" in " ".join(caught.value.errors)
