"""ETL-Synthea bootstrap: fixture-driven OMOP load + quality gate."""
from pathlib import Path

import pytest

from shp.omop import etl_synthea, schema, vocabulary as V
from shp.quality.checks import run_quality_gate

FIXTURE = Path(__file__).parent / "fixtures" / "synthea_csv"


@pytest.fixture
def omop_db(tmp_path):
    db = tmp_path / "synthea.duckdb"
    # Map two source codes so vocab coverage is a non-trivial number.
    cmap = {"44054006": V.CONCEPT_T2DM, "4548-4": V.CONCEPT_HBA1C}
    etl_synthea.etl(FIXTURE, db_path=db, concept_map=cmap)
    return db


def _count(db, table):
    con = schema.connect(db)
    try:
        return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    finally:
        con.close()


def test_person_load(omop_db):
    assert _count(omop_db, "person") == 3


def test_visits_and_classes(omop_db):
    con = schema.connect(omop_db)
    try:
        assert con.execute("SELECT count(*) FROM visit_occurrence").fetchone()[0] == 4
        # inpatient + emergency map to non-outpatient concepts
        ip = con.execute(
            f"SELECT count(*) FROM visit_occurrence WHERE visit_concept_id = {V.VISIT_INPATIENT}"
        ).fetchone()[0]
        er = con.execute(
            f"SELECT count(*) FROM visit_occurrence WHERE visit_concept_id = {V.VISIT_ER}"
        ).fetchone()[0]
        assert ip == 1 and er == 1
    finally:
        con.close()


def test_conditions_and_mapping(omop_db):
    con = schema.connect(omop_db)
    try:
        assert con.execute("SELECT count(*) FROM condition_occurrence").fetchone()[0] == 3
        # two T2DM rows mapped to the standard concept
        mapped = con.execute(
            f"SELECT count(*) FROM condition_occurrence WHERE condition_concept_id = {V.CONCEPT_T2DM}"
        ).fetchone()[0]
        assert mapped == 2
    finally:
        con.close()


def test_measurements_numeric_only(omop_db):
    # 3 numeric observations load; the text 'Body Height' row is dropped.
    assert _count(omop_db, "measurement") == 3


def test_death_loaded(omop_db):
    assert _count(omop_db, "death") == 1


def test_quality_gate_passes(omop_db):
    report = run_quality_gate(omop_db)
    assert report.passed, str(report)
    # coverage measured and between 0 and 1
    assert 0 < report.vocab_coverage["condition_occurrence"] <= 1.0
