import base64
import json
from pathlib import Path

SPEC_PATH = Path(__file__).resolve().parents[1] / "specs" / "ontology_debate.json"


def _spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def test_health(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_debate_spec_is_approved_by_a_person(client) -> None:
    created = client.post(
        "/artifacts",
        json={
            "kind": "debate_spec",
            "name": "ontology",
            "created_by": "rasika",
            "content_json": _spec(),
        },
    )
    assert created.status_code == 201, created.text
    artifact = created.json()
    assert artifact["version"] == 1
    assert artifact["kind"] == "debate_spec"

    proposed = client.post(
        "/proposals",
        json={
            "artifact_id": artifact["id"],
            "summary": "Lock the cross-vertical ontology debate. Phase 1 still materializes sales.",
            "submitted_by": "rasika",
        },
    )
    assert proposed.status_code == 201, proposed.text
    proposal = proposed.json()
    assert proposal["status"] == "pending"
    assert proposal["policy"] == "human_required"

    pending = client.get("/proposals", params={"status": "pending"})
    assert [row["id"] for row in pending.json()] == [proposal["id"]]

    decided = client.post(
        f"/proposals/{proposal['id']}/decision",
        json={
            "decision": "approved",
            "actor": "rasika",
            "reason": "Framework matches the taxonomy.",
        },
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["actor"] == "rasika"

    again = client.post(
        f"/proposals/{proposal['id']}/decision",
        json={"decision": "rejected", "actor": "rasika", "reason": "Too late."},
    )
    assert again.status_code == 409

    assert client.get("/proposals", params={"status": "pending"}).json() == []
    content = client.get(f"/artifacts/{artifact['id']}/content")
    assert content.status_code == 200
    assert content.json()["agreement"]["resolution"] == "argument_evaluation"
    assert content.json()["promotion"]["authority"] == "human"

    names = [span.name for span in client.app.state.exporter.get_finished_spans()]
    assert "artifact.put" in names
    assert "proposal.submit" in names
    assert "proposal.decide" in names


def test_missing_actor_and_foreign_policy_are_rejected(client) -> None:
    created = client.post(
        "/artifacts",
        json={
            "kind": "source_extract",
            "name": "levantia",
            "created_by": "rasika",
            "content_json": {"adapter": "levantia_erp"},
        },
    )
    assert created.status_code == 201, created.text
    proposed = client.post(
        "/proposals",
        json={
            "artifact_id": created.json()["id"],
            "summary": "Land the extract later.",
            "submitted_by": "rasika",
        },
    )
    proposal_id = proposed.json()["id"]
    missing_actor = client.post(
        f"/proposals/{proposal_id}/decision",
        json={"decision": "approved", "reason": "No one signed it."},
    )
    assert missing_actor.status_code == 422
    foreign_policy = client.post(
        "/proposals",
        json={
            "artifact_id": created.json()["id"],
            "summary": "Skip the person.",
            "submitted_by": "rasika",
            "policy": "auto",
        },
    )
    assert foreign_policy.status_code == 422


def test_dominant_debate_pattern_cannot_be_submitted(client) -> None:
    payload = _spec()
    payload["agreement"]["resolution"] = "majority_vote"
    response = client.post(
        "/artifacts",
        json={
            "kind": "debate_spec",
            "name": "ontology",
            "created_by": "rasika",
            "content_json": payload,
        },
    )
    assert response.status_code == 422
    assert "argument evaluation" in response.text


def test_versions_increase_and_bytes_roundtrip(client) -> None:
    first = client.post(
        "/artifacts",
        json={
            "kind": "source_extract",
            "name": "levantia",
            "created_by": "rasika",
            "content_base64": base64.b64encode(b"batch-1").decode(),
        },
    )
    second = client.post(
        "/artifacts",
        json={
            "kind": "source_extract",
            "name": "levantia",
            "created_by": "rasika",
            "content_base64": base64.b64encode(b"batch-2").decode(),
        },
    )
    assert first.json()["version"] == 1
    assert second.json()["version"] == 2
    assert client.get(f"/artifacts/{second.json()['id']}/content").content == b"batch-2"
