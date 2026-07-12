"""Starter OMOP vocabulary layer — runs the pipeline end-to-end without an Athena build.

This is deliberately a *starter* layer, not a shim to apologize for. The full OHDSI
vocabulary (Athena) is multi-GB, licence-gated (SNOMED etc.), and is the right
substrate for the **production** load — it cannot ship in a git repo or a Colab
notebook. So here we seed a curated concept set and a **validated crosswalk** for the
source codes we are confident of, and leave everything else as `concept_id = 0`
("no matching concept", the OMOP convention). Two honest consequences follow:

  * Standard-vocabulary coverage becomes a *measured number* the quality gate
    reports per domain — the real FHIR→OMOP work made visible, not hidden.
  * The crosswalk is the production seam: extend `reference/vocab/starter_crosswalk.csv`
    from an Athena/Usagi mapping pass (or swap to OHDSI ETL-Synthea / OMOP-on-FHIR,
    which write the same CDM with full vocabulary) and coverage climbs toward 100%.

Where we already know the real standard `concept_id` (gender, common LOINC/SNOMED,
OMOP type concepts) we use it, so a record ports to a full CDM unchanged. Study-local
concepts with no clean standard mapping use the OMOP-reserved range (>= 2e9) — exactly
how a real ETL parks unmapped source codes. See `docs/ARCHITECTURE.md` for the full
production vocabulary path (incl. the ICD-11 → SNOMED bridge for feeds that code in ICD-11).
"""
from __future__ import annotations

import csv
from pathlib import Path

import duckdb

# OMOP local/custom concept_id range begins here (per CDM convention).
LOCAL_CONCEPT_BASE = 2_000_000_000

# --- Standard concepts we rely on (real Athena ids) -------------------------
GENDER_FEMALE = 8532
GENDER_MALE = 8507
RACE_UNKNOWN = 0
ETHNICITY_UNKNOWN = 0

VISIT_OUTPATIENT = 9202
VISIT_INPATIENT = 9201
VISIT_ER = 9203

# Type concepts
TYPE_EHR = 32817                  # "EHR" (observation_period / measurement type)
TYPE_EHR_ENCOUNTER_DX = 32020     # "EHR encounter diagnosis" (condition type)
TYPE_PRESCRIPTION_WRITTEN = 32838 # "Prescription written" (drug type)

# Units
UNIT_PERCENT = 8554               # %
UNIT_MG_DL = 8840                 # mg/dL
UNIT_KG_M2 = 9531                 # kg/m2
UNIT_ML_MIN_173 = 8795            # mL/min  (eGFR reported per 1.73m2; approx)

# Common standard clinical concepts (real ids)
CONCEPT_T2DM = 201826             # Type 2 diabetes mellitus (SNOMED, standard)
CONCEPT_HBA1C = 3004410           # Hemoglobin A1c/Hemoglobin.total in Blood (LOINC, standard)

# --- Study-local concepts (no clean standard mapping in this shim) -----------
# Comorbidities
CONCEPT_CKD = LOCAL_CONCEPT_BASE + 10
CONCEPT_OBESITY = LOCAL_CONCEPT_BASE + 11
# Measurements / covariates carried as measurements
CONCEPT_EGFR = LOCAL_CONCEPT_BASE + 20
CONCEPT_BMI = LOCAL_CONCEPT_BASE + 21
CONCEPT_DM_DURATION = LOCAL_CONCEPT_BASE + 22
# Treatment arms — would resolve to ATC class concepts (ATC maps clean in OMOP).
CONCEPT_SGLT2 = LOCAL_CONCEPT_BASE + 30   # ATC A10BK
CONCEPT_SULFONYLUREA = LOCAL_CONCEPT_BASE + 31  # ATC A10BB
# SV-flavored social attribute used as a measured confounder.
CONCEPT_CKDU_REGION = LOCAL_CONCEPT_BASE + 40

_VOCABULARIES = [
    ("None", "OMOP standardized vocabularies (shim)", "", "phase2-shim-v0", 44819096),
    ("SNOMED", "SNOMED (subset shim)", "", "phase2-shim-v0", 44819097),
    ("LOINC", "LOINC (subset shim)", "", "phase2-shim-v0", 44819102),
    ("RxNorm", "RxNorm (subset shim)", "", "phase2-shim-v0", 44819104),
    ("ATC", "WHO ATC (subset shim)", "", "phase2-shim-v0", 44819117),
    ("Gender", "OMOP Gender", "", "phase2-shim-v0", 44819108),
    ("Visit", "OMOP Visit", "", "phase2-shim-v0", 44819119),
    ("Type Concept", "OMOP Type Concept", "", "phase2-shim-v0", 32812),
    ("UCUM", "Unified Code for Units of Measure (subset shim)", "", "phase2-shim-v0", 44819107),
    ("SHP-Local", "Study-local concepts (phase-2 sandbox)", "", "phase2-shim-v0", LOCAL_CONCEPT_BASE),
]

# (concept_id, name, domain, vocabulary, class, standard, code)
_CONCEPTS = [
    (0, "No matching concept", "Metadata", "None", "Undefined", None, "No matching concept"),
    (GENDER_FEMALE, "FEMALE", "Gender", "Gender", "Gender", "S", "F"),
    (GENDER_MALE, "MALE", "Gender", "Gender", "Gender", "S", "M"),
    (VISIT_OUTPATIENT, "Outpatient Visit", "Visit", "Visit", "Visit", "S", "OP"),
    (VISIT_INPATIENT, "Inpatient Visit", "Visit", "Visit", "Visit", "S", "IP"),
    (VISIT_ER, "Emergency Room Visit", "Visit", "Visit", "Visit", "S", "ER"),
    (TYPE_EHR, "EHR", "Type Concept", "Type Concept", "Type Concept", "S", "EHR"),
    (TYPE_EHR_ENCOUNTER_DX, "EHR encounter diagnosis", "Type Concept", "Type Concept", "Type Concept", "S", "EHR Dx"),
    (TYPE_PRESCRIPTION_WRITTEN, "Prescription written", "Type Concept", "Type Concept", "Type Concept", "S", "Rx written"),
    (UNIT_PERCENT, "percent", "Unit", "UCUM", "Unit", "S", "%"),
    (UNIT_MG_DL, "milligram per deciliter", "Unit", "UCUM", "Unit", "S", "mg/dL"),
    (UNIT_KG_M2, "kilogram per square meter", "Unit", "UCUM", "Unit", "S", "kg/m2"),
    (UNIT_ML_MIN_173, "milliliter per minute", "Unit", "UCUM", "Unit", "S", "mL/min"),
    (CONCEPT_T2DM, "Type 2 diabetes mellitus", "Condition", "SNOMED", "Clinical Finding", "S", "44054006"),
    (CONCEPT_HBA1C, "Hemoglobin A1c/Hemoglobin.total in Blood", "Measurement", "LOINC", "Lab Test", "S", "4548-4"),
    (CONCEPT_CKD, "Chronic kidney disease (study local)", "Condition", "SHP-Local", "Clinical Finding", None, "LOC-CKD"),
    (CONCEPT_OBESITY, "Obesity (study local)", "Condition", "SHP-Local", "Clinical Finding", None, "LOC-OBES"),
    (CONCEPT_EGFR, "Estimated GFR (study local)", "Measurement", "SHP-Local", "Lab Test", None, "LOC-EGFR"),
    (CONCEPT_BMI, "Body mass index (study local)", "Measurement", "SHP-Local", "Lab Test", None, "LOC-BMI"),
    (CONCEPT_DM_DURATION, "Diabetes duration, years (study local)", "Measurement", "SHP-Local", "Survey", None, "LOC-DMDUR"),
    (CONCEPT_SGLT2, "SGLT2 inhibitor (ATC A10BK, study local)", "Drug", "SHP-Local", "ATC 4th", "C", "A10BK"),
    (CONCEPT_SULFONYLUREA, "Sulfonylurea (ATC A10BB, study local)", "Drug", "SHP-Local", "ATC 4th", "C", "A10BB"),
    (CONCEPT_CKDU_REGION, "Residence in CKDu hotspot region (study local)", "Observation", "SHP-Local", "Survey", None, "LOC-CKDU-REG"),
]


def seed_core_vocab(con: duckdb.DuckDBPyConnection) -> None:
    """Insert vocabularies + the curated concept set. Idempotent."""
    con.execute("DELETE FROM vocabulary")
    con.executemany(
        """INSERT INTO vocabulary
           (vocabulary_id, vocabulary_name, vocabulary_reference,
            vocabulary_version, vocabulary_concept_id)
           VALUES (?, ?, ?, ?, ?)""",
        _VOCABULARIES,
    )
    con.execute("DELETE FROM concept")
    con.executemany(
        """INSERT INTO concept
           (concept_id, concept_name, domain_id, vocabulary_id, concept_class_id,
            standard_concept, concept_code, valid_start_date, valid_end_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, DATE '1970-01-01', DATE '2099-12-31')""",
        _CONCEPTS,
    )


def load_crosswalk(path) -> dict[str, int]:
    """Read a source-code → standard `concept_id` crosswalk CSV into a `concept_map`.

    Expected columns: `source_vocabulary, source_code, source_name,
    standard_concept_id, standard_concept_name, status`. Only rows with a non-zero
    `standard_concept_id` are returned — `0`/blank rows are explicit "not yet mapped"
    TODOs (the codes awaiting an Athena/Usagi pass), so they stay unmapped and show up
    in the coverage metric rather than being silently invented.

    The mapped `concept_id`s must also exist in the seeded `concept` table (they do for
    the bundled starter crosswalk); a production run seeds the full Athena `concept`.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"crosswalk not found: {path}")
    out: dict[str, int] = {}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            code = (row.get("source_code") or "").strip()
            raw = (row.get("standard_concept_id") or "0").strip()
            cid = int(raw) if raw.lstrip("-").isdigit() else 0
            if code and cid > 0:
                out[code] = cid
    return out
