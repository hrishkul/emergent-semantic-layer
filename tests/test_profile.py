from esl.profile import profile_extract
from esl.sources import erp_mtdd
from tests.erp_fixture import write_workbooks


def profile(tmp_path, defects):
    files = write_workbooks(tmp_path, defects=defects)
    return profile_extract(erp_mtdd.read_tables(files.seed), erp_mtdd.read_docs(files.schema))


def by_name(result, name):
    return next(t for t in result["tables"] if t["source_name"] == name)


def test_clean_extract_matches_its_documentation(tmp_path) -> None:
    result = profile(tmp_path, defects=False)
    summary = result["summary"]
    assert summary["primary_keys_ok"] == 2
    assert summary["tables_with_column_drift"] == []
    # The order with no customer is a null in a mandatory key, not an orphan.
    assert summary["relationship_status"] == {"mandatory_nulls": 1}
    credit = next(c for c in by_name(result, "Customers")["columns"] if c["name"] == "Credit_Limit")
    assert (credit["nulls"], credit["distinct"]) == (1, 2)


def test_planted_defects_are_reported(tmp_path) -> None:
    result = profile(tmp_path, defects=True)
    orders = by_name(result, "Sales Orders")
    assert orders["primary_key"] == {
        "documented": ["Sales_Order_ID"], "status": "violated",
        "null_rows": 0, "duplicate_rows": 2,
    }
    rel = result["relationships"][0]
    assert (rel["status"], rel["orphans"], rel["orphan_examples"]) == ("orphans", 1, [99])
    customers = by_name(result, "Customers")
    assert customers["columns_missing_from_data"] == ["Is_Active"]
    assert customers["columns_not_documented"] == ["Active_Flag"]
    assert result["summary"]["primary_keys_not_ok"] == ["Sales Orders"]
