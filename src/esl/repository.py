from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import psycopg


def public_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, UUID):
            out[key] = str(value)
        elif isinstance(value, datetime):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out


def insert_artifact(
    conn: psycopg.Connection,
    *,
    kind: str,
    name: str,
    created_by: str,
    content_uri: str,
    content_sha256: str,
) -> dict[str, Any]:
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s)::bigint)", (f"{kind}:{name}",))
    current = conn.execute(
        """
        SELECT COALESCE(MAX(version), 0) AS version
        FROM artifacts
        WHERE kind = %s AND logical_name = %s
        """,
        (kind, name),
    ).fetchone()
    version = int(current["version"]) + 1
    row = conn.execute(
        """
        INSERT INTO artifacts (
            id, kind, logical_name, version, content_uri, content_sha256, created_by
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, kind, logical_name, version, content_uri, content_sha256,
                  created_at, created_by
        """,
        (uuid4(), kind, name, version, content_uri, content_sha256, created_by),
    ).fetchone()
    return public_row(row)


def get_artifact(conn: psycopg.Connection, artifact_id: UUID) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT id, kind, logical_name, version, content_uri, content_sha256,
               created_at, created_by
        FROM artifacts
        WHERE id = %s
        """,
        (artifact_id,),
    ).fetchone()
    return public_row(row) if row else None


def insert_proposal(
    conn: psycopg.Connection,
    *,
    artifact_id: UUID,
    parent_artifact_id: UUID | None,
    summary: str,
    submitted_by: str,
) -> dict[str, Any]:
    row = conn.execute(
        """
        INSERT INTO proposals (
            id, artifact_id, parent_artifact_id, status, policy, summary, submitted_by
        )
        VALUES (%s, %s, %s, 'pending', 'human_required', %s, %s)
        RETURNING id, artifact_id, parent_artifact_id, status, policy, summary,
                  submitted_at, submitted_by
        """,
        (uuid4(), artifact_id, parent_artifact_id, summary, submitted_by),
    ).fetchone()
    return public_row(row)


def list_proposals(conn: psycopg.Connection, status: str | None) -> list[dict[str, Any]]:
    if status is None:
        rows = conn.execute(
            """
            SELECT id, artifact_id, parent_artifact_id, status, policy, summary,
                   submitted_at, submitted_by
            FROM proposals
            ORDER BY submitted_at
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, artifact_id, parent_artifact_id, status, policy, summary,
                   submitted_at, submitted_by
            FROM proposals
            WHERE status = %s
            ORDER BY submitted_at
            """,
            (status,),
        ).fetchall()
    return [public_row(row) for row in rows]


def decide_proposal(
    conn: psycopg.Connection,
    *,
    proposal_id: UUID,
    decision: str,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    proposal = conn.execute(
        "SELECT id, status FROM proposals WHERE id = %s FOR UPDATE",
        (proposal_id,),
    ).fetchone()
    if proposal is None:
        raise KeyError(str(proposal_id))
    if proposal["status"] != "pending":
        raise RuntimeError(proposal["status"])
    approval = conn.execute(
        """
        INSERT INTO approvals (id, proposal_id, decision, actor, reason)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id, proposal_id, decision, actor, reason, decided_at
        """,
        (uuid4(), proposal_id, decision, actor, reason),
    ).fetchone()
    conn.execute(
        "UPDATE proposals SET status = %s WHERE id = %s",
        (decision, proposal_id),
    )
    return public_row(approval)
