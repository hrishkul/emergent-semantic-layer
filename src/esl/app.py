import base64
import hashlib
import json
import os
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace.export import SpanExporter
from psycopg.errors import ForeignKeyViolation
from pydantic import BaseModel, ConfigDict, Field

from esl.db import connect
from esl.debate import DebateSpecError, parse_debate_spec
from esl.repository import (
    decide_proposal,
    get_artifact,
    insert_artifact,
    insert_proposal,
    list_proposals,
)
from esl.settings import Settings
from esl.store import ArtifactStore, DirectoryStore, S3Store
from esl.telemetry import build_tracer

Kind = Literal[
    "source_extract",
    "ontology",
    "kpi_registry",
    "cube_manifest",
    "debate_transcript",
    "debate_spec",
]


class CreateArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Kind
    name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")
    created_by: str = Field(min_length=1)
    content_base64: str | None = None
    content_json: dict | list | None = None

    def payload(self) -> bytes:
        if (self.content_base64 is None) == (self.content_json is None):
            raise ValueError("provide exactly one of content_base64 or content_json")
        if self.content_json is not None:
            return json.dumps(
                self.content_json,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        try:
            return base64.b64decode(self.content_base64 or "", validate=True)
        except Exception as exc:
            raise ValueError("content_base64 is not valid base64") from exc


class CreateProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: UUID
    parent_artifact_id: UUID | None = None
    summary: str = Field(min_length=1)
    submitted_by: str = Field(min_length=1)
    policy: Literal["human_required"] = "human_required"


class DecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approved", "rejected"]
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)


def build_store(settings: Settings) -> ArtifactStore:
    if settings.artifact_backend == "dir":
        return DirectoryStore(settings.artifact_dir)
    if settings.artifact_backend == "s3":
        store = S3Store(
            bucket=settings.s3_bucket,
            region=settings.s3_region,
            endpoint_url=settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
        )
        store.ensure_bucket()
        return store
    raise ValueError(f"unknown artifact backend: {settings.artifact_backend}")


def create_app(
    settings: Settings | None = None,
    exporter: SpanExporter | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    if exporter is None and os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        exporter = OTLPSpanExporter()
    app = FastAPI(title="Emergent semantic layer", version="0.1.0")
    app.state.settings = settings
    app.state.store = build_store(settings)
    app.state.tracer = build_tracer(exporter)

    def get_conn(request: Request):
        conn = connect(request.app.state.settings.database_url)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @app.get("/health")
    def health() -> JSONResponse:
        try:
            with connect(settings.database_url) as conn:
                conn.execute("SELECT 1")
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    @app.post("/artifacts", status_code=201)
    def create_artifact(body: CreateArtifact, request: Request, conn=Depends(get_conn)):
        try:
            data = body.payload()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if body.kind == "debate_spec":
            try:
                spec = parse_debate_spec(data)
            except DebateSpecError as exc:
                raise HTTPException(status_code=422, detail={"errors": exc.errors}) from exc
            if spec.name != body.name:
                raise HTTPException(
                    status_code=422,
                    detail="artifact name must match the spec name",
                )
            data = json.dumps(
                spec.model_dump(mode="json"),
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        digest = hashlib.sha256(data).hexdigest()
        key = f"{body.kind}/{body.name}/{digest}"
        with request.app.state.tracer.start_as_current_span("artifact.put") as span:
            span.set_attribute("artifact.kind", body.kind)
            span.set_attribute("artifact.name", body.name)
            uri = request.app.state.store.put(key, data)
            return insert_artifact(
                conn,
                kind=body.kind,
                name=body.name,
                created_by=body.created_by,
                content_uri=uri,
                content_sha256=digest,
            )

    @app.get("/artifacts/{artifact_id}")
    def read_artifact(artifact_id: UUID, conn=Depends(get_conn)):
        row = get_artifact(conn, artifact_id)
        if row is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return row

    @app.get("/artifacts/{artifact_id}/content")
    def read_content(artifact_id: UUID, request: Request, conn=Depends(get_conn)):
        row = get_artifact(conn, artifact_id)
        if row is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        try:
            data = request.app.state.store.get(row["content_uri"])
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="artifact bytes missing") from exc
        media = "application/json" if row["kind"] == "debate_spec" else "application/octet-stream"
        return Response(content=data, media_type=media)

    @app.post("/proposals", status_code=201)
    def create_proposal(body: CreateProposal, request: Request, conn=Depends(get_conn)):
        if get_artifact(conn, body.artifact_id) is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        with request.app.state.tracer.start_as_current_span("proposal.submit") as span:
            span.set_attribute("artifact.id", str(body.artifact_id))
            try:
                return insert_proposal(
                    conn,
                    artifact_id=body.artifact_id,
                    parent_artifact_id=body.parent_artifact_id,
                    summary=body.summary,
                    submitted_by=body.submitted_by,
                )
            except ForeignKeyViolation as exc:
                raise HTTPException(status_code=404, detail="artifact not found") from exc

    @app.get("/proposals")
    def read_proposals(conn=Depends(get_conn), status: str | None = None):
        if status is not None and status not in {"pending", "approved", "rejected", "superseded"}:
            raise HTTPException(status_code=422, detail="unknown proposal status")
        return list_proposals(conn, status)

    @app.post("/proposals/{proposal_id}/decision")
    def decide(proposal_id: UUID, body: DecisionBody, request: Request, conn=Depends(get_conn)):
        with request.app.state.tracer.start_as_current_span("proposal.decide") as span:
            span.set_attribute("proposal.id", str(proposal_id))
            span.set_attribute("proposal.decision", body.decision)
            try:
                return decide_proposal(
                    conn,
                    proposal_id=proposal_id,
                    decision=body.decision,
                    actor=body.actor,
                    reason=body.reason,
                )
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="proposal not found") from exc
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=409,
                    detail=f"proposal already {exc}",
                ) from exc

    return app


app = create_app()
