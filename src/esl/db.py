from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, row_factory=dict_row)


def statements(sql: str) -> list[str]:
    lines = [line for line in sql.splitlines() if not line.strip().startswith("--")]
    return [part.strip() for part in "\n".join(lines).split(";") if part.strip()]


def apply_migrations(database_url: str, directory: Path | None = None) -> list[str]:
    root = directory or MIGRATIONS
    applied: list[str] = []
    with connect(database_url) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        seen = {row["version"] for row in rows}
        for path in sorted(root.glob("*.sql")):
            if path.name in seen:
                continue
            for statement in statements(path.read_text()):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (%s)",
                (path.name,),
            )
            applied.append(path.name)
        conn.commit()
    return applied
