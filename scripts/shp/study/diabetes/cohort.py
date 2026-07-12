"""Reconstruct the diabetes analytic frame from OMOP (target-trial extraction).

Reads ONLY the standard CDM tables — exactly what the estimator stack would do
against ETL'd Synthea or real de-identified exhaust. Time-zero is the index drug
exposure; baseline covariates are the at-index measurements; the outcome is the
month-12 HbA1c minus the baseline HbA1c. The answer-key columns (_y0/_y1) are NOT
in OMOP, so this frame is exactly what an analyst would have in the real world.
"""
from __future__ import annotations

import pandas as pd

from ...omop import schema, vocabulary as V
from .dgp import COVARIATES

_SQL = f"""
WITH tx AS (   -- time-zero: index second-line drug
    SELECT person_id,
           MIN(drug_exposure_start_date) AS index_date,
           MAX(CASE WHEN drug_concept_id = {V.CONCEPT_SGLT2} THEN 1 ELSE 0 END) AS a
    FROM drug_exposure
    WHERE drug_concept_id IN ({V.CONCEPT_SGLT2}, {V.CONCEPT_SULFONYLUREA})
    GROUP BY person_id
),
base_hba1c AS (  -- baseline HbA1c at index
    SELECT m.person_id, m.value_as_number AS baseline_hba1c
    FROM measurement m JOIN tx ON tx.person_id = m.person_id
    WHERE m.measurement_concept_id = {V.CONCEPT_HBA1C}
      AND m.measurement_date = tx.index_date
),
fup_hba1c AS (   -- first HbA1c after index = month-12 follow-up
    SELECT m.person_id, m.value_as_number AS followup_hba1c
    FROM measurement m JOIN tx ON tx.person_id = m.person_id
    WHERE m.measurement_concept_id = {V.CONCEPT_HBA1C}
      AND m.measurement_date > tx.index_date
    QUALIFY ROW_NUMBER() OVER (PARTITION BY m.person_id ORDER BY m.measurement_date) = 1
),
cov AS (   -- at-index covariate measurements, pivoted
    SELECT person_id,
           MAX(CASE WHEN measurement_concept_id = {V.CONCEPT_EGFR}        THEN value_as_number END) AS egfr,
           MAX(CASE WHEN measurement_concept_id = {V.CONCEPT_BMI}         THEN value_as_number END) AS bmi,
           MAX(CASE WHEN measurement_concept_id = {V.CONCEPT_DM_DURATION} THEN value_as_number END) AS dm_duration,
           MAX(CASE WHEN measurement_concept_id = {V.CONCEPT_CKDU_REGION} THEN value_as_number END) AS ckdu_region
    FROM measurement
    GROUP BY person_id
),
ckd AS (
    SELECT DISTINCT person_id, 1 AS ckd
    FROM condition_occurrence WHERE condition_concept_id = {V.CONCEPT_CKD}
)
SELECT
    p.person_id,
    (EXTRACT(YEAR FROM tx.index_date) - p.year_of_birth)            AS age,
    ((EXTRACT(YEAR FROM tx.index_date) - p.year_of_birth) - 58)/11.0 AS age_z,
    CASE WHEN p.gender_concept_id = {V.GENDER_FEMALE} THEN 1 ELSE 0 END AS female,
    b.baseline_hba1c,
    cov.egfr, cov.bmi, cov.dm_duration,
    COALESCE(ck.ckd, 0)                                             AS ckd,
    COALESCE(cov.ckdu_region, 0)                                   AS ckdu_region,
    tx.a,
    (f.followup_hba1c - b.baseline_hba1c)                          AS y
FROM tx
JOIN person p       ON p.person_id = tx.person_id
JOIN base_hba1c b   ON b.person_id = tx.person_id
JOIN fup_hba1c f    ON f.person_id = tx.person_id
JOIN cov            ON cov.person_id = tx.person_id
LEFT JOIN ckd ck    ON ck.person_id = tx.person_id
ORDER BY p.person_id
"""


def build_analytic_frame(db_path) -> pd.DataFrame:
    con = schema.connect(db_path)
    try:
        df = con.execute(_SQL).fetch_df()
    finally:
        con.close()
    # Guarantee the estimator covariate columns exist and are ordered.
    missing = [c for c in COVARIATES if c not in df.columns]
    if missing:
        raise ValueError(f"cohort frame missing covariates: {missing}")
    return df
