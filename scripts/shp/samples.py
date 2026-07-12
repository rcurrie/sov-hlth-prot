"""Rebuild the two checked-in Colab samples from a full corpus.

The notebooks ship with a compact, git-friendly cohort so a researcher can open
them in Colab from a URL with no local build. Those two files are reproducible:

    OMOP/sv_sample100.duckdb    a stratified 100-person OMOP subset — keeps every
                                diabetes + CKD patient, tops up to 100 by lowest
                                person_id (the disease signal a demo needs).
    FHIR/sample_patient_fhir.json  one patient's Synthea FHIR R4 bundle, curated to
                                the clinical resources + numeric labs/vitals.

Inputs are the *full* artifacts you build locally (git-ignored, see the README):
    data/omop/sv.duckdb                     (from `shp etl`)
    data/build/run/output/fhir/*.json       (from `shp synthea generate`)

Neither input is required to *use* the notebooks — the samples are already
checked in. This command just lets you regenerate them.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import config

# SNOMED source codes that mark the disease signal we always keep in the subset.
# (Vocabulary is unmapped — every *_concept_id is 0 — so we match *_source_value.)
_T2DM = ["44054006"]
_CKD = ["431855005", "431856006", "433144002", "431857002", "46177005", "709044004"]
_SIGNAL_CODES = _T2DM + _CKD

# FHIR resource types worth keeping for a clinical/AI-fidelity single-patient view.
_KEEP_FHIR = {"Patient", "Encounter", "Condition", "MedicationRequest",
              "Immunization", "CarePlan", "Observation"}


def build_omop(src_db: Path | None = None, out_db: Path | None = None,
               target: int = 100) -> Path:
    """Cut a `target`-person stratified OMOP subset. Returns the output path."""
    import duckdb

    src_db = Path(src_db or config.SV_OMOP_DB)
    out_db = Path(out_db or config.SAMPLE_OMOP_DB)
    if not src_db.is_file():
        raise FileNotFoundError(
            f"full OMOP corpus not found at {src_db}. Build it first: "
            "`shp synthea generate` then `shp etl`.")
    out_db.parent.mkdir(parents=True, exist_ok=True)
    if out_db.exists():
        out_db.unlink()

    con = duckdb.connect(str(src_db), read_only=True)
    codes = ",".join(f"'{c}'" for c in _SIGNAL_CODES)
    signal = [r[0] for r in con.execute(
        f"SELECT DISTINCT person_id FROM condition_occurrence "
        f"WHERE condition_source_value IN ({codes})").fetchall()]
    keep = set(signal)
    if len(keep) < target:
        topup = con.execute(
            "SELECT person_id FROM person "
            "WHERE person_id NOT IN (SELECT DISTINCT person_id FROM condition_occurrence "
            f"  WHERE condition_source_value IN ({codes})) "
            "ORDER BY person_id LIMIT ?", [target - len(keep)]).fetchall()
        keep.update(r[0] for r in topup)
    ids = ",".join(str(i) for i in sorted(keep))

    # Only the canonical OMOP base tables. The ETL leaves `src_*` *views* over the
    # raw Synthea CSVs in the db; copying those would materialize ~20 MB of raw CSV
    # into the sample (and they reference local paths that don't exist elsewhere).
    tables = [r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='main' AND table_type='BASE TABLE' "
        "ORDER BY table_name").fetchall()]

    out = duckdb.connect(str(out_db))
    out.execute(f"ATTACH '{src_db}' AS src (READ_ONLY)")
    for t in tables:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info('{t}')").fetchall()]
        if "person_id" in cols:                         # patient-scoped: filter
            where = f"WHERE person_id IN ({ids})"
        elif "subject_id" in cols and t == "cohort":    # cohort is keyed by subject
            where = f"WHERE subject_id IN ({ids})"
        else:                                            # vocab / metadata: copy all
            where = ""
        out.execute(f"CREATE TABLE {t} AS SELECT * FROM src.{t} {where}")
    out.execute("DETACH src")
    n = out.execute("SELECT count(*) FROM person").fetchone()[0]
    out.close(); con.close()
    print(f"OMOP sample → {out_db}  ({n} persons, {len(signal)} with diabetes/CKD signal)")
    return out_db


def _numeric_obs(res: dict) -> bool:
    return "valueQuantity" in res and res["valueQuantity"].get("value") is not None


def _pick_bundle(bundles: list[Path], match: str | None,
                 size_cap: int = 40_000_000) -> Path:
    """Choose one patient bundle: a named match if given, else the patient with the
    richest *paired* glycemic + renal history (the diabetes→CKD story the notebook
    plots), among bundles small enough to stay git/Colab-friendly.

    We score by min(#HbA1c, #eGFR) readings so both trend charts have real data, and
    tie-break toward the smaller bundle. Substring counts on the raw text are cheap.
    """
    if match:
        for b in bundles:
            if match.lower() in b.read_text(encoding="utf-8").lower():
                return b
    best, best_score, best_size = None, -1, None
    for b in bundles:
        sz = b.stat().st_size
        if sz > size_cap:
            continue
        txt = b.read_text(encoding="utf-8")
        if "44054006" not in txt:                        # require T2DM
            continue
        score = min(txt.count("33914-3"), txt.count("4548-4"))   # eGFR & HbA1c readings
        if score > best_score or (score == best_score and best and sz < best_size):
            best, best_score, best_size = b, score, sz
    return best or sorted(bundles, key=lambda p: p.stat().st_size)[-1]


def build_fhir(src: Path | None = None, out_json: Path | None = None,
               match: str | None = None) -> Path:
    """Curate one patient's FHIR bundle down to clinical + numeric-lab resources."""
    out_json = Path(out_json or config.SAMPLE_FHIR_JSON)
    src = Path(src) if src else (config.BUILD_DIR / "run" / "output" / "fhir")

    if src.is_dir():
        bundles = sorted(src.glob("*.json"))
        if not bundles:
            raise FileNotFoundError(f"no FHIR bundles under {src}. Run `shp synthea generate`.")
        src = _pick_bundle(bundles, match)
    if not src.is_file():
        raise FileNotFoundError(f"FHIR source not found: {src}")

    bundle = json.loads(src.read_text(encoding="utf-8"))
    kept = []
    for entry in bundle.get("entry", []):
        res = entry.get("resource", {})
        rtype = res.get("resourceType")
        if rtype not in _KEEP_FHIR:
            continue
        if rtype == "Observation" and not _numeric_obs(res):
            continue                                    # drop non-numeric observations
        kept.append(entry)
    bundle["entry"] = kept

    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    mb = out_json.stat().st_size / 1e6
    print(f"FHIR sample → {out_json}  ({len(kept)} resources, {mb:.1f} MB, from {src.name})")
    return out_json


def build(*, omop: bool = True, fhir: bool = True, fhir_src=None) -> int:
    did = False
    if omop:
        build_omop(); did = True
    if fhir:
        try:
            build_fhir(src=fhir_src); did = True
        except FileNotFoundError as exc:
            print(f"skipping FHIR sample: {exc}")
    return 0 if did else 1
