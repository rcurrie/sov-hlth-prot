"""OMOP CDM v5.4 schema management on DuckDB."""
from __future__ import annotations

from pathlib import Path

import duckdb

from .. import config

_DDL_PATH = config.DDL_DIR / "omop_cdm_5_4_subset.sql"

# Tables created by the DDL, in dependency-free order (DuckDB has no FK enforcement
# here, but we use this list for truncation / counts).
CDM_TABLES = [
    "concept",
    "vocabulary",
    "concept_relationship",
    "cdm_source",
    "person",
    "observation_period",
    "visit_occurrence",
    "condition_occurrence",
    "drug_exposure",
    "measurement",
    "death",
    "cohort_definition",
    "cohort",
]

CLINICAL_EVENT_TABLES = [
    "person",
    "observation_period",
    "visit_occurrence",
    "condition_occurrence",
    "drug_exposure",
    "measurement",
    "death",
]


def connect(db_path: Path | str) -> duckdb.DuckDBPyConnection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def create_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Idempotently create the CDM subset."""
    con.execute(_DDL_PATH.read_text())


def reset_schema(con: duckdb.DuckDBPyConnection) -> None:
    """Drop and recreate every CDM table (a clean reload)."""
    for t in reversed(CDM_TABLES):
        con.execute(f"DROP TABLE IF EXISTS {t}")
    create_schema(con)


def fresh_db(db_path: Path | str) -> duckdb.DuckDBPyConnection:
    """Open `db_path`, wiping any prior CDM, and return a ready connection."""
    if Path(db_path).exists():
        Path(db_path).unlink()
    con = connect(db_path)
    create_schema(con)
    return con


def record_cdm_source(
    con: duckdb.DuckDBPyConnection,
    name: str,
    description: str,
    etl_reference: str,
) -> None:
    con.execute("DELETE FROM cdm_source WHERE cdm_source_name = ?", [name])
    con.execute(
        """
        INSERT INTO cdm_source
            (cdm_source_name, cdm_source_abbreviation, cdm_holder, source_description,
             cdm_etl_reference, cdm_version, cdm_version_concept_id, vocabulary_version)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [name, name, "Sovereign Health Protocol (SHP)", description, etl_reference,
         config.CDM_VERSION, 756265, "phase2-shim-v0"],
    )
