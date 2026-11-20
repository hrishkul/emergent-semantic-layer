import pytest

from esl.warehouse.bigquery import (
    BigQueryTarget,
    apply_bronze,
    bronze_statements,
    external_table_ddl,
    gcs_uri,
)

TARGET = BigQueryTarget("project-9a3d61d7-226e-4e0b-bad", "bronze_erp_mtdd")
MANIFEST = {
    "adapter": "erp_mtdd",
    "extract_id": "44b5f43d09d1b186",
    "source": {"dataset": "owner/name", "version": 11},
    "tables": [
        {"source_name": "Sales Orders", "table": "sales_orders", "rows": 70, "sha256": "ab",
         "uri": "s3://esl-bucket-01-enterprise/bronze/erp_mtdd/x/tables/sales_orders/ab.parquet"},
    ],
}


def test_store_uris_map_to_cloud_storage() -> None:
    assert gcs_uri("s3://b/k/x.parquet") == "gs://b/k/x.parquet"
    assert gcs_uri("gs://b/k") == "gs://b/k"
    with pytest.raises(ValueError, match="Cloud Storage"):
        gcs_uri("dir://bronze/x.parquet")


def test_external_table_statement() -> None:
    [statement] = bronze_statements(TARGET, MANIFEST)
    assert statement.startswith(
        "CREATE OR REPLACE EXTERNAL TABLE "
        "`project-9a3d61d7-226e-4e0b-bad.bronze_erp_mtdd.sales_orders`"
    )
    assert "format = 'PARQUET'" in statement
    assert "uris = ['gs://esl-bucket-01-enterprise/bronze/erp_mtdd/x/tables/" in statement
    assert "Sales Orders (70 rows)" in statement


def test_identifiers_are_validated() -> None:
    with pytest.raises(ValueError):
        external_table_ddl(TARGET, "orders`; DROP TABLE x", "gs://b/k", "")
    with pytest.raises(ValueError):
        BigQueryTarget("Bad Project", "bronze")
    with pytest.raises(ValueError):
        BigQueryTarget("project-9a3d61d7-226e-4e0b-bad", "bronze-dataset")
    assert '\\"' in external_table_ddl(TARGET, "t", "gs://b/k", 'a "quoted" note')


def test_apply_creates_dataset_then_tables() -> None:
    calls = []

    class Job:
        def result(self):
            return None

    class Client:
        def create_dataset(self, dataset, exists_ok):
            calls.append(("dataset", dataset.dataset_id, dataset.location, exists_ok))

        def query(self, sql, location):
            calls.append(("query", sql.splitlines()[0], location))
            return Job()

    created = apply_bronze(TARGET, MANIFEST, client=Client())
    assert created == ["project-9a3d61d7-226e-4e0b-bad.bronze_erp_mtdd.sales_orders"]
    assert calls[0] == ("dataset", "bronze_erp_mtdd", "us-central1", True)
    assert calls[1][0] == "query" and calls[1][2] == "us-central1"
