"""Profile a bronze extract against its own documentation.

The profile is evidence for the debate: what the data holds, and where it
disagrees with the documented keys, relationships, and columns.
"""

import re

import pandas as pd

from esl.bronze import slug


def profile_extract(tables: dict[str, pd.DataFrame], docs: dict[str, pd.DataFrame]) -> dict:
    index = docs.get("Table Index")
    dictionary = docs.get("Column Dictionary")
    relationships = docs.get("Relationships")

    keys = _documented_keys(index) if index is not None else {}
    documented = _documented_columns(dictionary) if dictionary is not None else {}

    table_profiles = [
        _profile_table(name, df, keys.get(name), documented.get(name))
        for name, df in sorted(tables.items())
    ]
    documented_only = sorted(set(keys) - set(tables))
    rel_checks = (
        [_check_relationship(row, tables) for row in relationships.to_dict("records")]
        if relationships is not None
        else []
    )

    return {
        "tables": table_profiles,
        "relationships": rel_checks,
        "documented_tables_without_data": documented_only,
        "summary": _summary(table_profiles, rel_checks, documented_only),
    }


def _profile_table(
    name: str,
    df: pd.DataFrame,
    key: list[str] | None,
    documented: list[str] | None,
) -> dict:
    columns = []
    for column in df.columns:
        series = df[column]
        nulls = int(series.isna().sum())
        distinct = int(series.nunique(dropna=True))
        columns.append(
            {
                "name": column,
                "dtype": str(series.dtype),
                "nulls": nulls,
                "distinct": distinct,
                "unique_non_null": bool(len(df) > 0 and nulls == 0 and distinct == len(df)),
            }
        )
    result: dict = {
        "source_name": name,
        "table": slug(name),
        "rows": int(len(df)),
        "columns": columns,
        "primary_key": _check_key(df, key),
    }
    if documented is not None:
        present = set(df.columns)
        result["columns_missing_from_data"] = [c for c in documented if c not in present]
        result["columns_not_documented"] = [c for c in df.columns if c not in set(documented)]
    return result


def _check_key(df: pd.DataFrame, key: list[str] | None) -> dict:
    if not key:
        return {"documented": None, "status": "undocumented"}
    missing = [c for c in key if c not in df.columns]
    if missing:
        return {"documented": key, "status": "missing_columns", "missing": missing}
    nulls = int(df[key].isna().any(axis=1).sum())
    duplicates = int(df.duplicated(subset=key, keep=False).sum())
    status = "ok" if nulls == 0 and duplicates == 0 else "violated"
    return {"documented": key, "status": status, "null_rows": nulls, "duplicate_rows": duplicates}


def _check_relationship(row: dict, tables: dict[str, pd.DataFrame]) -> dict:
    child, child_col = str(row["Child Table"]), str(row["Child Column"])
    parent, parent_key = str(row["Parent Table"]), str(row["Parent Key"])
    mandatory = str(row.get("Optional?", "")).strip().lower() == "mandatory"
    result = {
        "child": child,
        "child_column": child_col,
        "parent": parent,
        "parent_key": parent_key,
        "mandatory": mandatory,
        "cross_module": str(row.get("Cross-module?", "")).strip().lower() == "yes",
    }
    for table, column, side in ((child, child_col, "child"), (parent, parent_key, "parent")):
        if table not in tables:
            return {**result, "status": f"missing_{side}_table"}
        if column not in tables[table].columns:
            return {**result, "status": f"missing_{side}_column"}
    values = tables[child][child_col]
    present = values.dropna()
    parents = set(tables[parent][parent_key].dropna().tolist())
    orphans = present[~present.isin(parents)]
    null_count = int(values.isna().sum())
    status = "ok"
    if len(orphans):
        status = "orphans"
    elif mandatory and null_count:
        status = "mandatory_nulls"
    return {
        **result,
        "status": status,
        "child_rows": int(len(values)),
        "nulls": null_count,
        "orphans": int(len(orphans)),
        "orphan_examples": [_plain(v) for v in orphans.unique()[:5]],
    }


def _documented_keys(index: pd.DataFrame) -> dict[str, list[str]]:
    keys = {}
    for row in index.to_dict("records"):
        name, key = row.get("Table Name"), row.get("Primary Key")
        if pd.isna(name) or str(name).strip().upper() == "TOTAL":
            continue
        parts = [] if pd.isna(key) else [p for p in re.split(r"[,+/]", str(key)) if p.strip()]
        keys[str(name)] = [p.strip() for p in parts]
    return keys


def _documented_columns(dictionary: pd.DataFrame) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in dictionary.to_dict("records"):
        table, column = row.get("Table"), row.get("Column Name")
        if pd.isna(table) or pd.isna(column):
            continue
        out.setdefault(str(table), []).append(str(column))
    return out


def _summary(tables: list[dict], rels: list[dict], documented_only: list[str]) -> dict:
    statuses: dict[str, int] = {}
    for rel in rels:
        statuses[rel["status"]] = statuses.get(rel["status"], 0) + 1
    return {
        "tables": len(tables),
        "rows": sum(t["rows"] for t in tables),
        "primary_keys_ok": sum(t["primary_key"]["status"] == "ok" for t in tables),
        "primary_keys_not_ok": [
            t["source_name"] for t in tables if t["primary_key"]["status"] != "ok"
        ],
        "relationships": len(rels),
        "relationship_status": dict(sorted(statuses.items())),
        "tables_with_column_drift": [
            t["source_name"]
            for t in tables
            if t.get("columns_missing_from_data") or t.get("columns_not_documented")
        ],
        "documented_tables_without_data": documented_only,
    }


def _plain(value: object) -> object:
    return value.item() if hasattr(value, "item") else value
