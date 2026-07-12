"""Synthea CSV → OMOP CDM v5.4 — a lightweight DuckDB bootstrap ETL.

Scope & honesty: this is the *fast* converter that gets a matched FHIR+OMOP set
running today, covering the core clinical domains (person, observation_period,
visit, condition, drug, measurement, death). It is NOT a vocabulary mapper. Synthea
source codes (SNOMED / RxNorm / LOINC) are loaded as `*_source_value` with
`*_concept_id = 0` ("no matching concept") unless an explicit `concept_map` is
supplied. That makes standard-vocabulary coverage a *measured* number the quality
gate reports — which is precisely the napkin-plan flag: "FHIR→OMOP coverage is the
real work; ICD-11→OMOP mapping is immature."

The validated production path is OHDSI **ETL-Synthea** (with full Athena vocab) or
**OMOP-on-FHIR** for the real de-id exhaust; both write the same CDM this reads.
Swap them in by pointing the estimator stack at their OMOP instance — nothing
downstream changes. Wire Athena here by passing `concept_map={source_code: concept_id}`.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

from .. import config
from . import schema, vocabulary as V

# Synthea CSV files we consume (others ignored for now).
EXPECTED = ["patients", "encounters", "conditions", "medications", "observations"]


def _csv(con, name: str, csv_dir: Path) -> bool:
    """Register a Synthea CSV as a view `src_<name>`. Returns False if absent."""
    path = csv_dir / f"{name}.csv"
    if not path.exists():
        return False
    con.execute(
        f"CREATE OR REPLACE VIEW src_{name} AS "
        f"SELECT * FROM read_csv_auto('{path}', header=true, all_varchar=true)"
    )
    return True


_SOURCE_DESCRIPTIONS = {
    config.CDM_SOURCE_SV:
        "El Salvador-calibrated Synthea corpus (synthea + nemotron personas)",
    config.CDM_SOURCE_DIABETES:
        "Semi-synthetic diabetes cohort with a known injected treatment effect",
}


def etl(csv_dir, db_path=None, source_name: str | None = None,
        source_description: str | None = None,
        concept_map: dict[str, int] | None = None) -> str:
    """Convert a Synthea CSV directory into a fresh OMOP DuckDB. Returns the path."""
    csv_dir = Path(csv_dir)
    db_path = str(db_path or config.SV_OMOP_DB)
    source_name = source_name or config.CDM_SOURCE_SV
    source_description = source_description or _SOURCE_DESCRIPTIONS.get(
        source_name, f"Synthea CSV load ({source_name})")
    config.ensure_dirs()

    con = schema.fresh_db(db_path)
    V.seed_core_vocab(con)
    schema.record_cdm_source(con, source_name, source_description,
                             "shp.omop.etl_synthea")

    present = {n: _csv(con, n, csv_dir) for n in EXPECTED}
    if not present.get("patients"):
        raise FileNotFoundError(f"No patients.csv in {csv_dir}")

    # Map Synthea UUIDs → integer person_ids.
    con.execute("""
        CREATE TEMP TABLE pat_xref AS
        SELECT Id AS src_id, ROW_NUMBER() OVER (ORDER BY Id) AS person_id
        FROM src_patients
    """)
    _cmap_table(con, concept_map)

    _load_person(con)
    _load_observation_period(con, present)
    if present.get("encounters"):
        _load_visits(con)
    if present.get("conditions"):
        _load_conditions(con)
    if present.get("medications"):
        _load_medications(con)
    if present.get("observations"):
        _load_measurements(con)
    _load_death(con)

    con.close()
    return db_path


def _cmap_table(con, concept_map):
    con.execute("CREATE TEMP TABLE cmap (source_code VARCHAR, concept_id BIGINT)")
    if concept_map:
        con.executemany("INSERT INTO cmap VALUES (?, ?)",
                        [(str(k), int(v)) for k, v in concept_map.items()])


def _D(col):  # parse a Synthea ISO timestamp/date string → DATE
    return f"TRY_CAST(substr({col}, 1, 10) AS DATE)"


def _load_person(con):
    con.execute(f"""
        INSERT INTO person
            (person_id, gender_concept_id, year_of_birth, month_of_birth, day_of_birth,
             birth_datetime, race_concept_id, ethnicity_concept_id,
             person_source_value, gender_source_value, race_source_value, ethnicity_source_value)
        SELECT x.person_id,
               CASE WHEN p.GENDER = 'M' THEN {V.GENDER_MALE}
                    WHEN p.GENDER = 'F' THEN {V.GENDER_FEMALE} ELSE 0 END,
               EXTRACT(YEAR  FROM {_D('p.BIRTHDATE')}),
               EXTRACT(MONTH FROM {_D('p.BIRTHDATE')}),
               EXTRACT(DAY   FROM {_D('p.BIRTHDATE')}),
               TRY_CAST(p.BIRTHDATE AS TIMESTAMP),
               {V.RACE_UNKNOWN}, {V.ETHNICITY_UNKNOWN},
               p.Id, p.GENDER, p.RACE, p.ETHNICITY
        FROM src_patients p JOIN pat_xref x ON x.src_id = p.Id
    """)


def _load_observation_period(con, present):
    # Span = earliest to latest event we loaded, per person (fallback to birthdate).
    con.execute(f"""
        INSERT INTO observation_period
            (observation_period_id, person_id, observation_period_start_date,
             observation_period_end_date, period_type_concept_id)
        WITH ev AS (
            SELECT x.person_id,
                   MIN({_D('e.START')}) AS s, MAX(COALESCE({_D('e.STOP')}, {_D('e.START')})) AS e
            FROM src_encounters e JOIN pat_xref x ON x.src_id = e.PATIENT
            GROUP BY x.person_id
        )
        SELECT x.person_id, x.person_id,
               COALESCE(ev.s, {_D('p.BIRTHDATE')}),
               COALESCE(ev.e, CURRENT_DATE),
               {V.TYPE_EHR}
        FROM pat_xref x
        JOIN src_patients p ON p.Id = x.src_id
        LEFT JOIN ev ON ev.person_id = x.person_id
    """)


def _load_visits(con):
    con.execute(f"""
        INSERT INTO visit_occurrence
            (visit_occurrence_id, person_id, visit_concept_id, visit_start_date,
             visit_end_date, visit_type_concept_id, visit_source_value)
        SELECT ROW_NUMBER() OVER (ORDER BY e.Id), x.person_id,
               CASE lower(e.ENCOUNTERCLASS)
                    WHEN 'inpatient'  THEN {V.VISIT_INPATIENT}
                    WHEN 'emergency'  THEN {V.VISIT_ER}
                    WHEN 'urgentcare' THEN {V.VISIT_ER}
                    ELSE {V.VISIT_OUTPATIENT} END,
               {_D('e.START')}, COALESCE({_D('e.STOP')}, {_D('e.START')}),
               {V.TYPE_EHR}, e.ENCOUNTERCLASS
        FROM src_encounters e JOIN pat_xref x ON x.src_id = e.PATIENT
    """)


def _load_conditions(con):
    con.execute(f"""
        INSERT INTO condition_occurrence
            (condition_occurrence_id, person_id, condition_concept_id, condition_start_date,
             condition_end_date, condition_type_concept_id, condition_source_value,
             condition_source_concept_id)
        SELECT ROW_NUMBER() OVER (ORDER BY c.PATIENT, c.START, c.CODE), x.person_id,
               COALESCE(m.concept_id, 0), {_D('c.START')}, {_D('c.STOP')},
               {V.TYPE_EHR_ENCOUNTER_DX}, c.CODE, 0
        FROM src_conditions c JOIN pat_xref x ON x.src_id = c.PATIENT
        LEFT JOIN cmap m ON m.source_code = c.CODE
    """)


def _load_medications(con):
    con.execute(f"""
        INSERT INTO drug_exposure
            (drug_exposure_id, person_id, drug_concept_id, drug_exposure_start_date,
             drug_exposure_end_date, drug_type_concept_id, drug_source_value, drug_source_concept_id)
        SELECT ROW_NUMBER() OVER (ORDER BY md.PATIENT, md.START, md.CODE), x.person_id,
               COALESCE(m.concept_id, 0), {_D('md.START')}, {_D('md.STOP')},
               {V.TYPE_PRESCRIPTION_WRITTEN}, md.CODE, 0
        FROM src_medications md JOIN pat_xref x ON x.src_id = md.PATIENT
        LEFT JOIN cmap m ON m.source_code = md.CODE
    """)


def _load_measurements(con):
    # Only numeric observations become measurements.
    con.execute(f"""
        INSERT INTO measurement
            (measurement_id, person_id, measurement_concept_id, measurement_date,
             measurement_type_concept_id, value_as_number, measurement_source_value,
             measurement_source_concept_id, unit_source_value)
        SELECT ROW_NUMBER() OVER (ORDER BY o.PATIENT, o.DATE, o.CODE), x.person_id,
               COALESCE(m.concept_id, 0), {_D('o.DATE')},
               {V.TYPE_EHR}, TRY_CAST(o.VALUE AS DOUBLE), o.CODE, 0, o.UNITS
        FROM src_observations o JOIN pat_xref x ON x.src_id = o.PATIENT
        LEFT JOIN cmap m ON m.source_code = o.CODE
        WHERE TRY_CAST(o.VALUE AS DOUBLE) IS NOT NULL
          AND lower(coalesce(o.TYPE, 'numeric')) = 'numeric'
    """)


def _load_death(con):
    con.execute(f"""
        INSERT INTO death (person_id, death_date, death_type_concept_id)
        SELECT x.person_id, {_D('p.DEATHDATE')}, {V.TYPE_EHR}
        FROM src_patients p JOIN pat_xref x ON x.src_id = p.Id
        WHERE p.DEATHDATE IS NOT NULL AND length(trim(p.DEATHDATE)) >= 10
    """)
