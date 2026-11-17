import io

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from esl.bronze import land_extract, slug
from esl.sources import erp_mtdd
from esl.store import DirectoryStore
from tests.erp_fixture import write_workbooks


def land(store, files):
    return land_extract(
        store,
        adapter=erp_mtdd.ADAPTER,
        source={"dataset": erp_mtdd.DATASET, "version": erp_mtdd.VERSION},
        raw_files=[files.seed, files.schema],
        tables=erp_mtdd.read_tables(files.seed),
        docs=erp_mtdd.read_docs(files.schema),
    )


def read(store, uri):
    return pq.read_table(io.BytesIO(store.get(uri)))


def test_extract_lands_tables_docs_and_raw(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    files = write_workbooks(tmp_path / "src")
    store = DirectoryStore(tmp_path / "store")
    manifest = land(store, files)

    assert [t["table"] for t in manifest["tables"]] == ["customers", "sales_orders"]
    assert manifest["totals"] == {"tables": 2, "rows": 7}
    assert {d["source_name"] for d in manifest["docs"]} == set(erp_mtdd.DOC_SHEETS)
    raw = {entry["name"]: entry for entry in manifest["raw"]}
    assert store.get(raw[files.seed.name]["uri"]) == files.seed.read_bytes()
    assert store.get(raw[files.schema.name]["uri"]) == files.schema.read_bytes()

    orders = read(store, manifest["tables"][1]["uri"])
    assert orders.num_rows == 4
    assert orders.schema.field("Customer_ID").type == pa.int64()
    assert orders.schema.field("Order_Date").type == pa.string()
    assert orders.column("Customer_ID").null_count == 1
    assert manifest["uri"].startswith(f"dir://bronze/erp_mtdd/{manifest['extract_id']}/manifest/")


def test_rerun_is_identical_and_writes_nothing_new(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    files = write_workbooks(tmp_path / "src")
    store = DirectoryStore(tmp_path / "store")
    first = land(store, files)
    before = sorted(p for p in (tmp_path / "store").rglob("*") if p.is_file())
    second = land(store, files)
    after = sorted(p for p in (tmp_path / "store").rglob("*") if p.is_file())
    assert first == second
    assert before == after


def test_names_that_collide_are_refused(tmp_path) -> None:
    import pandas as pd

    frame = pd.DataFrame({"a": [1]})
    with pytest.raises(ValueError, match="both become"):
        land_extract(
            DirectoryStore(tmp_path), adapter="x", source={}, raw_files=[],
            tables={"Sales Orders": frame, "sales-orders": frame}, docs={},
        )


def test_slug() -> None:
    assert slug("Units of Measure") == "units_of_measure"
    assert slug("AR Aging Reports") == "ar_aging_reports"
    assert slug("Lot/Serial Numbers") == "lot_serial_numbers"
    assert slug("2025 Budgets") == "t_2025_budgets"
