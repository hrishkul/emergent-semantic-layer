"""KPI registry artifact. Each KPI is one measure on one ontology node."""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from esl.ontology import DocumentLink, Ontology
from esl.schema import SchemaError, canonical_json

_ID = r"^[a-z][a-z0-9_]{0,62}$"
_COLUMN = r"^[A-Za-z][A-Za-z0-9_]*$"


class Measure(BaseModel):
    """A column as it landed in bronze. The compiler turns this into SQL later."""

    model_config = ConfigDict(extra="forbid")

    table: str = Field(pattern=_ID)
    column: str = Field(pattern=_COLUMN)


class Kpi(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_ID)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    node: str = Field(pattern=_ID)
    aggregation: Literal["sum", "count", "count_distinct"]
    measure: Measure
    grain: str = Field(min_length=1)
    documents: list[DocumentLink] = Field(min_length=1)


class KpiRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    ontology_name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    kpis: list[Kpi] = Field(min_length=1)


def parse_kpi_registry(data: bytes) -> KpiRegistry:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise SchemaError([f"kpi registry is not json: {exc.msg}"]) from exc
    try:
        registry = KpiRegistry.model_validate(payload)
    except ValidationError as exc:
        raise SchemaError([err["msg"] for err in exc.errors()]) from exc
    enforce_registry(registry)
    return registry


def enforce_registry(registry: KpiRegistry) -> None:
    ids = [kpi.id for kpi in registry.kpis]
    if len(ids) != len(set(ids)):
        raise SchemaError(["kpi ids must be unique"])


def check_against_ontology(registry: KpiRegistry, ontology: Ontology) -> None:
    """The two artifacts are stored apart. This checks a pair before it is proposed."""

    errors: list[str] = []
    if registry.ontology_name != ontology.name:
        errors.append("ontology_name must match the ontology name")
    nodes = {node.id: node for node in ontology.nodes}
    for kpi in registry.kpis:
        node = nodes.get(kpi.node)
        if node is None:
            errors.append(f"{kpi.id} names unknown node {kpi.node}")
            continue
        tables = {table.name for table in node.tables}
        if kpi.measure.table not in tables:
            errors.append(
                f"{kpi.id} measure table {kpi.measure.table} is not a table of {kpi.node}"
            )
    if errors:
        raise SchemaError(errors)


def registry_bytes(registry: KpiRegistry) -> bytes:
    return canonical_json(registry)
