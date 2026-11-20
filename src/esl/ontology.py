"""Ontology artifact: nodes, edges, and links to tables and documents.

The artifact is the system of record. A graph database is not.
"""

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from esl.schema import SchemaError, canonical_json

DOC_SHEETS = (
    "Table Index",
    "Dependency Register",
    "Complexity Rules",
    "Column Dictionary",
    "Relationships",
    "Load Order",
)

# Contested by more than one vertical. The sales slice still has to name them.
FOUNDATION_NODES = ("customer", "item", "legal_entity", "order", "invoice", "stock")

_ID = r"^[a-z][a-z0-9_]{0,62}$"
_COLUMN = r"^[A-Za-z][A-Za-z0-9_]*$"


class DocumentLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheet: Literal[
        "Table Index",
        "Dependency Register",
        "Complexity Rules",
        "Column Dictionary",
        "Relationships",
        "Load Order",
    ]
    locator: str = Field(min_length=1)


class TableLink(BaseModel):
    """A bronze table. ``name`` is the landed slug; ``source_name`` is the workbook table."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=_ID)
    source_name: str = Field(min_length=1)
    role: Literal["authoritative", "duplicate"]


class Node(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_ID)
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    grain: str = Field(min_length=1)
    tables: list[TableLink] = Field(min_length=1)
    documents: list[DocumentLink] = Field(min_length=1)


class Edge(BaseModel):
    """A foreign key. ``source`` holds ``column``; ``target`` is the referenced node."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_ID)
    source: str = Field(pattern=_ID)
    target: str = Field(pattern=_ID)
    name: str = Field(pattern=_ID)
    description: str = Field(min_length=1)
    column: str = Field(pattern=_COLUMN)
    documents: list[DocumentLink] = Field(min_length=1)


class Ontology(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    slice: Literal["sales"]
    shared_foundation: Literal[True]
    nodes: list[Node] = Field(min_length=1)
    edges: list[Edge] = Field(min_length=1)


def parse_ontology(data: bytes) -> Ontology:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise SchemaError([f"ontology is not json: {exc.msg}"]) from exc
    try:
        ontology = Ontology.model_validate(payload)
    except ValidationError as exc:
        raise SchemaError([err["msg"] for err in exc.errors()]) from exc
    enforce_ontology(ontology)
    return ontology


def enforce_ontology(ontology: Ontology) -> None:
    errors: list[str] = []
    if ontology.slice != "sales" or not ontology.shared_foundation:
        errors.append("phase 1 ontology is the sales slice plus shared foundation")
    ids = [node.id for node in ontology.nodes]
    if len(ids) != len(set(ids)):
        errors.append("node ids must be unique")
    missing = [node_id for node_id in FOUNDATION_NODES if node_id not in ids]
    if missing:
        errors.append("shared foundation nodes missing: " + ", ".join(missing))
    known = set(ids)
    edge_ids = [edge.id for edge in ontology.edges]
    if len(edge_ids) != len(set(edge_ids)):
        errors.append("edge ids must be unique")
    for node in ontology.nodes:
        authoritative = [table for table in node.tables if table.role == "authoritative"]
        if len(authoritative) != 1:
            errors.append(f"{node.id} needs exactly one authoritative table")
    for edge in ontology.edges:
        if edge.source not in known or edge.target not in known:
            errors.append(f"{edge.id} must connect two nodes in this ontology")
        elif edge.source == edge.target:
            errors.append(f"{edge.id} cannot connect a node to itself")
    if errors:
        raise SchemaError(errors)


def ontology_bytes(ontology: Ontology) -> bytes:
    return canonical_json(ontology)
