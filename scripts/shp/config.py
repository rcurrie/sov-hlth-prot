"""Central configuration for the OMOP / estimator side of the pipeline.

Nothing here is PHI. This consumes the Synthea CSV that the SV pipeline
(`shp synthea generate`) writes under ``data/build/run/output/csv``,
converts it to OMOP CDM v5.4 (DuckDB), and runs the estimator stack. The
semi-synthetic diabetes study needs no Synthea/Java at all.

Layout convention (shared with ``shp.synthea.config``):
    checked-in inputs  -> repo root  (config/, modules/, reference/)
    generated / large  -> data/      (git-ignored, reproducible)
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths.  scripts/shp/config.py  ->  parents[2] == repo root.
# ---------------------------------------------------------------------------
PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parents[1]              # sov-hlth-prot/
DDL_DIR = PKG_DIR / "omop" / "ddl"

DATA_DIR = REPO_ROOT / "data"               # git-ignored
BUILD_DIR = DATA_DIR / "build"              # Synthea run dir + run/output/{csv,fhir}
VENDOR_DIR = DATA_DIR / "vendor"            # downloaded Synthea jar
OMOP_DIR = DATA_DIR / "omop"                # *.duckdb OMOP databases

# Checked-in sample cohort that the Colab notebooks read.
SAMPLE_OMOP_DB = REPO_ROOT / "OMOP" / "sv_sample100.duckdb"
SAMPLE_FHIR_JSON = REPO_ROOT / "FHIR" / "sample_patient_fhir.json"

# Starter source-code → standard concept_id crosswalk (the vocabulary-mapping seam).
STARTER_CROSSWALK = REPO_ROOT / "reference" / "vocab" / "starter_crosswalk.csv"

# ---------------------------------------------------------------------------
# OMOP CDM
# ---------------------------------------------------------------------------
CDM_VERSION = "5.4"
CDM_SOURCE_SV = "synthea-nemotron-sv"       # OMOP built from the SV corpus
CDM_SOURCE_DIABETES = "diabetes-semisynthetic"

SV_OMOP_DB = OMOP_DIR / "sv.duckdb"         # full corpus OMOP db
DIABETES_OMOP_DB = OMOP_DIR / "diabetes_study.duckdb"


def synthea_csv_dir():
    """Locate the SV pipeline's Synthea CSV export under ``data/build``, or None.

    Synthea writes ``run/output/csv/patients.csv``; we glob so we're resilient to
    exactly how the run directory is arranged.
    """
    for hint in (BUILD_DIR / "run" / "output" / "csv",
                 BUILD_DIR / "output" / "csv",
                 BUILD_DIR / "csv"):
        if (hint / "patients.csv").is_file():
            return hint
    if BUILD_DIR.is_dir():
        for cand in sorted(BUILD_DIR.rglob("csv/patients.csv")):
            return cand.parent
    return None


def ensure_dirs() -> None:
    for d in (BUILD_DIR, VENDOR_DIR, OMOP_DIR):
        d.mkdir(parents=True, exist_ok=True)
