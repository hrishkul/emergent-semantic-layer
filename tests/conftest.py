import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from esl.app import create_app
from esl.db import apply_migrations
from esl.settings import Settings

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://esl:esl@127.0.0.1:5432/esl")


@pytest.fixture(scope="session")
def database_url() -> str:
    apply_migrations(DATABASE_URL)
    return DATABASE_URL


@pytest.fixture
def client(database_url: str, tmp_path: Path) -> Iterator[TestClient]:
    with psycopg.connect(database_url) as conn:
        conn.execute("TRUNCATE artifacts, proposals, approvals, runs CASCADE")
        conn.commit()
    exporter = InMemorySpanExporter()
    app = create_app(
        Settings(
            database_url=database_url,
            artifact_backend="dir",
            artifact_dir=tmp_path / "artifacts",
        ),
        exporter=exporter,
    )
    app.state.exporter = exporter
    with TestClient(app) as test_client:
        yield test_client
