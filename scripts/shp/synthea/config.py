"""Central configuration: paths, dataset coordinates, and SV reference constants.

Nothing here is PHI. Every value is either a public dataset coordinate or a
public administrative fact about El Salvador.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths.  scripts/shp/synthea/config.py  ->  parents[3] == repo root.
#   Checked-in inputs live at the repo root (config/, modules/, reference/).
#   Everything generated or downloaded lives under data/  (git-ignored).
# ---------------------------------------------------------------------------
PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parents[2]            # sov-hlth-prot/
DATA_DIR = REPO_ROOT / "data"             # git-ignored, reproducible artifacts
PERSONAS_DIR = DATA_DIR / "personas"      # cached Nemotron parquet shards
CENSUS_DIR = REPO_ROOT / "reference" / "census"   # checked-in calibration inputs
BURDEN_DIR = REPO_ROOT / "reference" / "burden"   # checked-in calibration inputs
MODULES_DIR = REPO_ROOT / "modules"
CONFIG_DIR = REPO_ROOT / "config"
BUILD_DIR = DATA_DIR / "build"            # generated Synthea inputs + run/output
VENDOR_DIR = DATA_DIR / "vendor"          # downloaded Synthea fat-jar


def ensure_dirs() -> None:
    for d in (PERSONAS_DIR, BUILD_DIR, VENDOR_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Nemotron-Personas-El-Salvador (the demographic spine)
#   https://huggingface.co/datasets/nvidia/Nemotron-Personas-El-Salvador
#   CC BY 4.0 · 148,000 rows · 3 parquet shards
# ---------------------------------------------------------------------------
HF_DATASET = "nvidia/Nemotron-Personas-El-Salvador"
HF_PARQUET_BASE = (
    "https://huggingface.co/datasets/nvidia/Nemotron-Personas-El-Salvador"
    "/resolve/refs%2Fconvert%2Fparquet/default/train"
)
PERSONA_SHARDS = ["0000.parquet", "0001.parquet", "0002.parquet"]

# Columns that form the demographic "spine" we bind a synthetic patient to.
SPINE_COLUMNS = [
    "uuid",
    "sex",
    "age",
    "marital_status",
    "household_type",
    "education_level",
    "occupation",
    "area",          # urbano / rural
    "municipality",
    "department",
]
# Rich free-text persona columns used to seed Spanish-language narratives.
NARRATIVE_COLUMNS = [
    "persona",
    "professional_persona",
    "family_persona",
    "cultural_background",
]

# ---------------------------------------------------------------------------
# El Salvador administrative reference (14 departments)
# Capital and largest department: San Salvador.
# ---------------------------------------------------------------------------
DEPARTMENTS = [
    "Ahuachapán", "Santa Ana", "Sonsonate", "Chalatenango", "La Libertad",
    "San Salvador", "Cuscatlán", "La Paz", "Cabañas", "San Vicente",
    "Usulután", "San Miguel", "Morazán", "La Unión",
]

# Departments in the hot Pacific lowland / sugarcane belt where CKDu
# (Mesoamerican nephropathy) clusters. Used to target the CKDu risk attribute.
# Bajo Lempa (Usulután / La Paz / San Vicente) is the canonical hotspot.
CKDU_HOTSPOT_DEPARTMENTS = ["Usulután", "La Paz", "San Vicente", "San Miguel", "La Unión"]

ISO_COUNTRY = "SV"
