"""Source adapter for the Kaggle ERP seed dataset (adapter name ``erp_mtdd``).

Two workbooks: the seed data (one sheet per table) and the schema
documentation (column dictionary, relationships, load order, and more).
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

ADAPTER = "erp_mtdd"
DATASET = "moutasmtamimi/dataset-erp-system-modules-tables-dependency"
VERSION = 11
SEED_FILE = "ERP_Seed_Data (1).xlsx"
SCHEMA_FILE = "ERP_Schema_v2_Corrected (1).xlsx"
SEED_INDEX_SHEET = "Index"
DOC_SHEETS = (
    "Table Index",
    "Dependency Register",
    "Complexity Rules",
    "Column Dictionary",
    "Relationships",
    "Load Order",
)


@dataclass(frozen=True)
class SourceFiles:
    seed: Path
    schema: Path

    @classmethod
    def in_directory(cls, directory: Path) -> "SourceFiles":
        files = cls(seed=directory / SEED_FILE, schema=directory / SCHEMA_FILE)
        missing = [p.name for p in (files.seed, files.schema) if not p.is_file()]
        if missing:
            raise FileNotFoundError(f"missing source files in {directory}: {', '.join(missing)}")
        return files


def download(version: int = VERSION) -> SourceFiles:
    import kagglehub

    path = kagglehub.dataset_download(f"{DATASET}/versions/{version}")
    return SourceFiles.in_directory(Path(path))


def read_tables(seed: Path) -> dict[str, pd.DataFrame]:
    sheets = pd.read_excel(seed, sheet_name=None)
    sheets.pop(SEED_INDEX_SHEET, None)
    return {name: _bronze_types(df) for name, df in sheets.items()}


def read_docs(schema: Path) -> dict[str, pd.DataFrame]:
    sheets = pd.read_excel(schema, sheet_name=list(DOC_SHEETS))
    return {name: _bronze_types(df) for name, df in sheets.items()}


def _bronze_types(df: pd.DataFrame) -> pd.DataFrame:
    # Nullable types keep integer keys as integers when a value is missing.
    df = df.convert_dtypes(dtype_backend="numpy_nullable")
    df.columns = [str(c) for c in df.columns]
    return df
