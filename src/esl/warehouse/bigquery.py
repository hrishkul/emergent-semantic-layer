"""BigQuery bronze: one external table per landed Parquet file."""

import re
from dataclasses import dataclass

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")
_PROJECT = re.compile(r"^[a-z][a-z0-9-]{4,61}[a-z0-9]$")


@dataclass(frozen=True)
class BigQueryTarget:
    project: str
    dataset: str
    location: str = "us-central1"

    def __post_init__(self) -> None:
        if not _PROJECT.match(self.project):
            raise ValueError(f"not a BigQuery project id: {self.project!r}")
        _identifier(self.dataset)


def gcs_uri(uri: str) -> str:
    """Map a store URI to the gs:// URI BigQuery reads.

    The S3 driver reports ``s3://bucket/key``. On Cloud Storage that is the
    same object as ``gs://bucket/key``.
    """
    if uri.startswith("gs://"):
        return uri
    if uri.startswith("s3://"):
        return "gs://" + uri[len("s3://") :]
    raise ValueError(f"BigQuery cannot read {uri!r}; land the extract in Cloud Storage first")


def external_table_ddl(target: BigQueryTarget, table: str, uri: str, description: str) -> str:
    _identifier(table)
    location = gcs_uri(uri).replace("'", "")
    note = description.replace("\\", "\\\\").replace('"', '\\"')
    return (
        f"CREATE OR REPLACE EXTERNAL TABLE `{target.project}.{target.dataset}.{table}`\n"
        f"OPTIONS (\n"
        f"  format = 'PARQUET',\n"
        f"  uris = ['{location}'],\n"
        f'  description = "{note}"\n'
        f")"
    )


def bronze_statements(target: BigQueryTarget, manifest: dict) -> list[str]:
    source = manifest["source"]
    statements = []
    for entry in manifest["tables"]:
        description = (
            f"Bronze {manifest['adapter']} extract {manifest['extract_id']}: "
            f"{entry['source_name']} ({entry['rows']} rows) from "
            f"{source.get('dataset')} version {source.get('version')}. sha256 {entry['sha256']}."
        )
        statements.append(external_table_ddl(target, entry["table"], entry["uri"], description))
    return statements


def apply_bronze(target: BigQueryTarget, manifest: dict, client=None) -> list[str]:
    """Create the dataset if needed, then (re)create every external table."""
    from google.cloud import bigquery

    client = client or bigquery.Client(project=target.project)
    dataset = bigquery.Dataset(f"{target.project}.{target.dataset}")
    dataset.location = target.location
    dataset.description = f"Bronze external tables for the {manifest['adapter']} adapter."
    client.create_dataset(dataset, exists_ok=True)
    created = []
    for entry, statement in zip(manifest["tables"], bronze_statements(target, manifest)):
        client.query(statement, location=target.location).result()
        created.append(f"{target.project}.{target.dataset}.{entry['table']}")
    return created


def _identifier(value: str) -> str:
    if not _IDENT.match(value):
        raise ValueError(f"not a BigQuery identifier: {value!r}")
    return value
