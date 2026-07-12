"""Assemble an SV run directory and run Synthea (fat-jar model).

The run directory contains everything Synthea will resolve from the filesystem:
  geography/  sv_demographics.csv, sv_zipcodes.csv
  providers/  sv_hospitals.csv, sv_primary_care.csv
  payers/     sv_insurance_{companies,plans,eligibilities}.csv
  modules_sv/ dengue.json, ckdu_mesoamerican_nephropathy.json
  sv_synthea.properties

Then runs:
  java -jar synthea-with-dependencies.jar -c sv_synthea.properties \
       -d modules_sv -p <N> -s <seed> "El Salvador"

"El Salvador" is the positional *state* argument — without it Synthea defaults to
a US state and can't resolve the SV abbreviation/geography.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import bootstrap, config

STATE = "El Salvador"
PROPERTIES_TEMPLATE = config.CONFIG_DIR / "synthea.properties"
PAYERS_DIR = config.CONFIG_DIR / "payers"


def run_dir() -> Path:
    return config.BUILD_DIR / "run"


def stage(target: Path | None = None) -> dict:
    """Assemble the run directory from generated geography + project config."""
    rd = Path(target or run_dir())
    geo_src = config.BUILD_DIR / "synthea" / "geography"
    prov_src = config.BUILD_DIR / "synthea" / "providers"
    for need in (geo_src / "sv_demographics.csv", geo_src / "sv_zipcodes.csv",
                 prov_src / "sv_hospitals.csv"):
        if not need.exists():
            raise RuntimeError(f"missing {need}; run the geography step first")

    layout = {
        "geography": [geo_src / "sv_demographics.csv", geo_src / "sv_zipcodes.csv"],
        "providers": [prov_src / "sv_hospitals.csv", prov_src / "sv_primary_care.csv"],
        "payers": sorted(PAYERS_DIR.glob("*.csv")),
        "modules_sv": sorted(config.MODULES_DIR.glob("*.json")),
    }
    for subdir, files in layout.items():
        d = rd / subdir
        d.mkdir(parents=True, exist_ok=True)
        for f in files:
            shutil.copy2(f, d / f.name)
    shutil.copy2(PROPERTIES_TEMPLATE, rd / "sv_synthea.properties")

    return {
        "run_dir": str(rd),
        "geography": [f.name for f in layout["geography"]],
        "providers": [f.name for f in layout["providers"]],
        "payers": [f.name for f in layout["payers"]],
        "modules": [f.name for f in layout["modules_sv"]],
    }


def _count_outputs(rd: Path) -> dict:
    out = rd / "output"
    counts = {}
    fhir = out / "fhir"
    if fhir.exists():
        counts["fhir_files"] = sum(1 for _ in fhir.glob("*.json"))
    csv = out / "csv"
    if csv.exists():
        counts["csv_files"] = sorted(p.name for p in csv.glob("*.csv"))
    return counts


def run(population: int = 1000, seed: int = 1, *, dry_run: bool = False,
        target: Path | None = None) -> dict:
    """Run (or describe) a Synthea generation for El Salvador."""
    rd = Path(target or run_dir())
    jar = bootstrap.JAR_PATH
    cmd = ["java", "-jar", str(jar), "-c", "sv_synthea.properties",
           "-d", "modules_sv", "-p", str(population), "-s", str(seed), STATE]
    manifest = {
        "command": " ".join(cmd),
        "cwd": str(rd),
        "population": population,
        "seed": seed,
        "output_dir": str(rd / "output"),
    }
    java = bootstrap.check_java()
    manifest["java"] = java
    manifest["jar_present"] = jar.exists()

    config.BUILD_DIR.mkdir(parents=True, exist_ok=True)
    (config.BUILD_DIR / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")

    if dry_run or not java or not jar.exists():
        manifest["status"] = ("blocked: no JDK" if not java
                              else "blocked: no jar (run bootstrap)" if not jar.exists()
                              else "dry-run")
        if not java:
            manifest["hint"] = bootstrap.JAVA_HINT
        return manifest

    proc = subprocess.run(cmd, cwd=rd, capture_output=True, text=True,
                          env=bootstrap.java_env())
    manifest["status"] = "ok" if proc.returncode == 0 else "failed"
    manifest["returncode"] = proc.returncode
    manifest["stdout_tail"] = proc.stdout[-1500:]
    manifest["stderr_tail"] = proc.stderr[-1500:]
    manifest["outputs"] = _count_outputs(rd)
    (config.BUILD_DIR / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
