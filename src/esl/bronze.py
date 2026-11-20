"""Land a source extract in the artifact store as bronze.

Layout under ``bronze/<adapter>/<extract id>/``:
``raw/`` the original files, ``tables/<table>/<sha256>.parquet`` one file per
table, ``docs/<sheet>/<sha256>.parquet`` one file per documentation sheet, and
``manifest/<sha256>.json``. Derived files carry their hash in the path, because
the store never overwrites a key.
"""

import hashlib
import io
import json
import re
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from esl.store import ArtifactStore


def slug(name: str) -> str:
    value = re.sub(r"[^0-9a-zA-Z]+", "_", name).strip("_").lower()
    if not value:
        raise ValueError(f"cannot make a table name from {name!r}")
    return value if not value[0].isdigit() else f"t_{value}"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parquet_bytes(df: pd.DataFrame) -> bytes:
    table = pa.Table.from_pandas(df, preserve_index=False)
    # Plain string and binary: the types every Parquet reader accepts, BigQuery included.
    narrow = {pa.large_string(): pa.string(), pa.large_binary(): pa.binary()}
    schema = pa.schema(
        [field.with_type(narrow.get(field.type, field.type)) for field in table.schema],
        metadata=table.schema.metadata,
    )
    if any(field.type == pa.null() for field in schema):
        empty = [field.name for field in schema if field.type == pa.null()]
        raise ValueError(f"columns with no values and no type: {', '.join(empty)}")
    buffer = io.BytesIO()
    pq.write_table(table.cast(schema), buffer)
    return buffer.getvalue()


def extract_id(file_hashes: dict[str, str]) -> str:
    joined = "\n".join(f"{name}:{digest}" for name, digest in sorted(file_hashes.items()))
    return sha256(joined.encode())[:16]


def land_extract(
    store: ArtifactStore,
    *,
    adapter: str,
    source: dict,
    raw_files: list[Path],
    tables: dict[str, pd.DataFrame],
    docs: dict[str, pd.DataFrame],
) -> dict:
    raw = {path.name: path.read_bytes() for path in raw_files}
    hashes = {name: sha256(data) for name, data in raw.items()}
    eid = extract_id(hashes)
    prefix = f"bronze/{adapter}/{eid}"

    raw_entries = [
        {"name": name, "sha256": hashes[name], "bytes": len(data),
         "uri": store.put(f"{prefix}/raw/{name}", data)}
        for name, data in sorted(raw.items())
    ]
    table_entries = [
        _land_frame(store, f"{prefix}/tables", name, df) for name, df in sorted(tables.items())
    ]
    doc_entries = [
        _land_frame(store, f"{prefix}/docs", name, df) for name, df in sorted(docs.items())
    ]
    _check_unique(table_entries, "table")
    _check_unique(doc_entries, "doc")

    manifest = {
        "adapter": adapter,
        "extract_id": eid,
        "source": source,
        "raw": raw_entries,
        "tables": table_entries,
        "docs": doc_entries,
        "totals": {
            "tables": len(table_entries),
            "rows": sum(t["rows"] for t in table_entries),
        },
    }
    body = canonical_json(manifest)
    return {**manifest, "uri": store.put(f"{prefix}/manifest/{sha256(body)}.json", body)}


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()


def _land_frame(store: ArtifactStore, prefix: str, name: str, df: pd.DataFrame) -> dict:
    data = parquet_bytes(df)
    table = slug(name)
    digest = sha256(data)
    return {
        "source_name": name,
        "table": table,
        "rows": int(len(df)),
        "columns": [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns],
        "sha256": digest,
        "uri": store.put(f"{prefix}/{table}/{digest}.parquet", data),
    }


def _check_unique(entries: list[dict], label: str) -> None:
    seen: dict[str, str] = {}
    for entry in entries:
        other = seen.setdefault(entry["table"], entry["source_name"])
        if other != entry["source_name"]:
            raise ValueError(
                f"{label} names {other!r} and {entry['source_name']!r} "
                f"both become {entry['table']!r}"
            )
