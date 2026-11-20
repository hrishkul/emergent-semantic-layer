import json
import os
from pathlib import Path

import pytest

from esl.bronze import slug
from esl.corpus import passages_from_docs
from esl.kpi import check_against_ontology, parse_kpi_registry
from esl.ontology import DOC_SHEETS, DocumentLink, parse_ontology
from esl.schema import SchemaError
from esl.sources.erp_mtdd import DOC_SHEETS as SOURCE_SHEETS
from esl.sources.erp_mtdd import SCHEMA_FILE, read_docs

ROOT = Path(__file__).resolve().parents[1]
ONTOLOGY_PATH = ROOT / "specs" / "ontology_erp_mtdd.json"
REGISTRY_PATH = ROOT / "specs" / "kpi_registry_erp_mtdd.json"


def _ontology() -> dict:
    return json.loads(ONTOLOGY_PATH.read_text())


def _registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text())


def test_sheet_names_match_the_schema_workbook() -> None:
    assert DOC_SHEETS == SOURCE_SHEETS
    for sheet in DOC_SHEETS:
        DocumentLink(sheet=sheet, locator="x")


def test_hand_written_ontology_and_kpis_validate() -> None:
    ontology = parse_ontology(ONTOLOGY_PATH.read_bytes())
    registry = parse_kpi_registry(REGISTRY_PATH.read_bytes())
    check_against_ontology(registry, ontology)
    for node in ontology.nodes:
        for table in node.tables:
            assert slug(table.source_name) == table.name


def test_ontology_requires_the_shared_foundation(client) -> None:
    payload = _ontology()
    payload["nodes"] = [node for node in payload["nodes"] if node["id"] != "stock"]
    payload["edges"] = [
        edge for edge in payload["edges"] if edge["source"] != "stock" and edge["target"] != "stock"
    ]
    response = client.post(
        "/artifacts",
        json={
            "kind": "ontology",
            "name": "erp-mtdd",
            "created_by": "rasika",
            "content_json": payload,
        },
    )
    assert response.status_code == 422
    assert "stock" in response.text


def test_ontology_is_stored_as_json(client) -> None:
    created = client.post(
        "/artifacts",
        json={
            "kind": "ontology",
            "name": "erp-mtdd",
            "created_by": "rasika",
            "content_json": _ontology(),
        },
    )
    assert created.status_code == 201, created.text
    content = client.get(f"/artifacts/{created.json()['id']}/content")
    assert content.headers["content-type"].startswith("application/json")
    assert content.json()["slice"] == "sales"
    assert {node["id"] for node in content.json()["nodes"]} >= {
        "customer",
        "item",
        "legal_entity",
        "order",
        "invoice",
        "stock",
    }

    registry = client.post(
        "/artifacts",
        json={
            "kind": "kpi_registry",
            "name": "erp-mtdd",
            "created_by": "rasika",
            "content_json": _registry(),
        },
    )
    assert registry.status_code == 201, registry.text
    body = client.get(f"/artifacts/{registry.json()['id']}/content").json()
    assert [kpi["id"] for kpi in body["kpis"]] == [
        "booked_value",
        "invoiced_revenue",
        "quoted_value",
    ]


def test_kpi_measure_must_sit_on_its_node() -> None:
    ontology = parse_ontology(ONTOLOGY_PATH.read_bytes())
    payload = _registry()
    payload["kpis"][0]["measure"]["table"] = "customers"
    registry = parse_kpi_registry(json.dumps(payload).encode())
    with pytest.raises(SchemaError, match="booked_value"):
        check_against_ontology(registry, ontology)


def _workbook() -> Path | None:
    candidates = []
    if os.environ.get("ERP_MTDD_DIR"):
        candidates.append(Path(os.environ["ERP_MTDD_DIR"]) / SCHEMA_FILE)
    cache = Path.home() / ".cache/kagglehub/datasets"
    cache = cache / "moutasmtamimi/dataset-erp-system-modules-tables-dependency"
    candidates.append(cache / "versions/11" / SCHEMA_FILE)
    return next((path for path in candidates if path.is_file()), None)


def test_hand_written_links_cite_real_passages() -> None:
    workbook = _workbook()
    if workbook is None:
        pytest.skip("schema workbook is not on this machine")
    passages = {(p.sheet, p.locator) for p in passages_from_docs(read_docs(workbook))}
    ontology = parse_ontology(ONTOLOGY_PATH.read_bytes())
    registry = parse_kpi_registry(REGISTRY_PATH.read_bytes())
    cited = [
        (link.sheet, link.locator)
        for node in ontology.nodes
        for link in node.documents
    ]
    cited += [
        (link.sheet, link.locator)
        for edge in ontology.edges
        for link in edge.documents
    ]
    cited += [
        (link.sheet, link.locator)
        for kpi in registry.kpis
        for link in kpi.documents
    ]
    missing = [
        f"{sheet} / {locator}"
        for sheet, locator in cited
        if (sheet, locator) not in passages
    ]
    assert missing == []
