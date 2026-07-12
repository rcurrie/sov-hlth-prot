"""Materialize the semi-synthetic diabetes cohort as OMOP CDM v5.4 records.

We do NOT hand the estimators a convenient flat file. We write the cohort into
real OMOP tables (person, observation_period, visit_occurrence, condition_occurrence,
drug_exposure, measurement) and make the estimator stack reconstruct its analytic
frame by querying OMOP — the same path it will take against ETL'd Synthea and, later,
real de-identified exhaust. Time-zero is the index drug initiation (target-trial style).
"""
from __future__ import annotations

from datetime import date, timedelta

import duckdb

from ... import config
from .. import diabetes  # noqa: F401  (package marker)
from ...omop import schema, vocabulary as V
from .dgp import DiabetesCohort

# Cohort/time-zero anchoring. Deterministic (no wall-clock) so loads are reproducible.
_ANCHOR = date(2022, 1, 1)
_FOLLOWUP_DAYS = 365
COHORT_DEFINITION_ID = 1
COHORT_NAME = "T2DM second-line initiators (SGLT2 vs SU) — semi-synthetic"


def _index_date(person_id: int) -> date:
    return _ANCHOR + timedelta(days=person_id % 300)


def load(cohort: DiabetesCohort, db_path=None) -> str:
    """Write the cohort to a fresh OMOP DuckDB and return its path."""
    db_path = str(db_path or config.DIABETES_OMOP_DB)
    config.ensure_dirs()
    con = schema.fresh_db(db_path)
    V.seed_core_vocab(con)
    schema.record_cdm_source(
        con, config.CDM_SOURCE_DIABETES,
        "Semi-synthetic T2DM CER cohort with injected ATE (answer-key for estimator validation)",
        "estimator_stack.study.diabetes.to_omop",
    )

    df = cohort.df.reset_index(drop=True)
    persons, obs_periods, visits, conditions, drugs, measurements = [], [], [], [], [], []
    cohort_rows = []

    cid = did = vid = mid = 1
    for pid, row in df.iterrows():
        person_id = int(pid) + 1
        idx = _index_date(person_id)
        fup = idx + timedelta(days=_FOLLOWUP_DAYS)
        yob = idx.year - int(round(row["age"]))
        gender = V.GENDER_FEMALE if row["female"] == 1 else V.GENDER_MALE

        persons.append((person_id, gender, yob, 1, 1, V.RACE_UNKNOWN, V.ETHNICITY_UNKNOWN,
                        f"dm-{person_id}", "F" if row["female"] == 1 else "M"))
        obs_periods.append((person_id, person_id, idx, fup + timedelta(days=30), V.TYPE_EHR))
        # one index visit + one follow-up visit
        visits.append((vid, person_id, V.VISIT_OUTPATIENT, idx, idx, V.TYPE_EHR)); vid += 1
        visits.append((vid, person_id, V.VISIT_OUTPATIENT, fup, fup, V.TYPE_EHR)); vid += 1

        # Index condition: T2DM (defines the cohort). CKD if present.
        conditions.append((cid, person_id, V.CONCEPT_T2DM, idx, V.TYPE_EHR_ENCOUNTER_DX, "44054006")); cid += 1
        if int(row["ckd"]) == 1:
            conditions.append((cid, person_id, V.CONCEPT_CKD, idx, V.TYPE_EHR_ENCOUNTER_DX, "LOC-CKD")); cid += 1
        if float(row["bmi"]) >= 30:
            conditions.append((cid, person_id, V.CONCEPT_OBESITY, idx, V.TYPE_EHR_ENCOUNTER_DX, "LOC-OBES")); cid += 1

        # Index treatment (time-zero): arm.
        drug = V.CONCEPT_SGLT2 if int(row["a"]) == 1 else V.CONCEPT_SULFONYLUREA
        drugs.append((did, person_id, drug, idx, fup, V.TYPE_PRESCRIPTION_WRITTEN,
                      "A10BK" if int(row["a"]) == 1 else "A10BB")); did += 1

        # Baseline measurements at index.
        for concept, val, unit in (
            (V.CONCEPT_HBA1C, float(row["baseline_hba1c"]), V.UNIT_PERCENT),
            (V.CONCEPT_EGFR, float(row["egfr"]), V.UNIT_ML_MIN_173),
            (V.CONCEPT_BMI, float(row["bmi"]), V.UNIT_KG_M2),
            (V.CONCEPT_DM_DURATION, float(row["dm_duration"]), None),
            (V.CONCEPT_CKDU_REGION, float(row["ckdu_region"]), None),
        ):
            measurements.append((mid, person_id, concept, idx, V.TYPE_EHR, val, unit)); mid += 1
        # Follow-up HbA1c at month 12 = baseline + observed ΔHbA1c.
        followup_hba1c = float(row["baseline_hba1c"]) + float(row["y"])
        measurements.append((mid, person_id, V.CONCEPT_HBA1C, fup, V.TYPE_EHR, followup_hba1c, V.UNIT_PERCENT)); mid += 1

        cohort_rows.append((COHORT_DEFINITION_ID, person_id, idx, fup + timedelta(days=30)))

    _bulk(con, "person",
          "person_id, gender_concept_id, year_of_birth, month_of_birth, day_of_birth, "
          "race_concept_id, ethnicity_concept_id, person_source_value, gender_source_value",
          persons)
    _bulk(con, "observation_period",
          "observation_period_id, person_id, observation_period_start_date, "
          "observation_period_end_date, period_type_concept_id", obs_periods)
    _bulk(con, "visit_occurrence",
          "visit_occurrence_id, person_id, visit_concept_id, visit_start_date, "
          "visit_end_date, visit_type_concept_id", visits)
    _bulk(con, "condition_occurrence",
          "condition_occurrence_id, person_id, condition_concept_id, condition_start_date, "
          "condition_type_concept_id, condition_source_value", conditions)
    _bulk(con, "drug_exposure",
          "drug_exposure_id, person_id, drug_concept_id, drug_exposure_start_date, "
          "drug_exposure_end_date, drug_type_concept_id, drug_source_value", drugs)
    _bulk(con, "measurement",
          "measurement_id, person_id, measurement_concept_id, measurement_date, "
          "measurement_type_concept_id, value_as_number, unit_concept_id", measurements)

    con.execute(
        "INSERT INTO cohort_definition "
        "(cohort_definition_id, cohort_definition_name, cohort_definition_description) "
        "VALUES (?, ?, ?)",
        [COHORT_DEFINITION_ID, COHORT_NAME, "Index = second-line drug initiation; ΔHbA1c at 12m."],
    )
    _bulk(con, "cohort",
          "cohort_definition_id, subject_id, cohort_start_date, cohort_end_date", cohort_rows)

    con.close()
    return db_path


def _bulk(con: duckdb.DuckDBPyConnection, table: str, columns: str, rows: list[tuple]) -> None:
    if not rows:
        return
    placeholders = ", ".join(["?"] * len(rows[0]))
    con.executemany(f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", rows)
