"""Turn the SV disease-burden table into Synthea calibration directives.

For the two modules we author here (dengue, CKDu) the directive also carries the
*currently authored* value pulled straight from the module JSON, so a mismatch
between the calibration target and the module is surfaced as a TODO rather than
silently diverging. For the built-in Synthea chronic-disease modules (diabetes,
hypertension, ...) we only emit the target prevalence + where to apply it.

Synthetic != evidence: these numbers shape generation only. Each carries its
source and a confidence flag from data/burden/sv_disease_burden.csv.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from . import config


def load_burden() -> list[dict]:
    path = config.BURDEN_DIR / "sv_disease_burden.csv"
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _authored_distribution(module_file: str, state: str, transition: str):
    """Pull the authored distribution for a state's transition target, if present."""
    p = config.MODULES_DIR / module_file
    if not p.exists():
        return None
    obj = json.loads(p.read_text(encoding="utf-8"))
    st = obj.get("states", {}).get(state, {})
    for t in st.get("distributed_transition", []):
        if t.get("transition") == transition:
            return t.get("distribution")
    return None


# Map a (burden key, sex) -> (module_file, state, transition target) it should drive.
# Sex matters for CKDu: the male hotspot prevalence drives the high-risk roll,
# the female prevalence drives the female baseline roll.
AUTHORED_KNOBS = {
    ("dengue", "A"):        ("dengue.json", "Infection_Roll", "Symptom_Encounter"),
    ("dengue_severe", "A"): ("dengue.json", "Severity_Branch", "Severe_Dengue"),
    ("ckdu", "M"): ("ckdu_mesoamerican_nephropathy.json", "Roll_High_Risk", "CKDu_Encounter"),
    ("ckdu", "F"): ("ckdu_mesoamerican_nephropathy.json", "Roll_Female_Baseline", "CKDu_Encounter"),
}

# Built-in Synthea modules to recalibrate (not authored here) and where.
BUILTIN_TARGETS = {
    "diabetes": "metabolic_syndrome_disease.json / diabetes prevalence lookup",
    "hypertension": "hypertension/* submodule prevalence",
    "dyslipidemia": "metabolic_syndrome_* lipid prevalence",
    "obesity": "metabolic_syndrome / BMI distribution",
    "ckd": "chronic_kidney_disease submodule prevalence",
}


def build_directives() -> list[dict]:
    directives = []
    for row in load_burden():
        key = row["key"]
        target = float(row["value"])
        unit = row["unit"]
        # normalize incidence-per-100k to an annual probability
        if unit == "per_100k_yr":
            target_prob = round(target / 100_000.0, 6)
        else:
            target_prob = round(target, 6)

        d = {
            "condition": row["condition"],
            "key": key,
            "sex": row["sex"],
            "age_range": f"{row['age_min']}-{row['age_max']}",
            "target": target,
            "unit": unit,
            "target_probability": target_prob,
            "source": row["source"],
            "confidence": row["confidence"],
            "notes": row["notes"],
        }
        knob = AUTHORED_KNOBS.get((key, row["sex"]))
        if knob:
            mod, state, trans = knob
            authored = _authored_distribution(mod, state, trans)
            d["applies_to"] = f"module:{mod} state:{state} -> {trans}"
            d["authored_value"] = authored
            d["status"] = (
                "ok" if authored is not None and abs(authored - target_prob) < 1e-6
                else "REVIEW: authored value differs from target"
                if authored is not None else "not-yet-applied"
            )
        elif key in BUILTIN_TARGETS:
            d["applies_to"] = f"builtin:{BUILTIN_TARGETS[key]}"
            d["status"] = "recalibrate-builtin (out of v0 scope: CKDu+dengue authored)"
        else:
            d["applies_to"] = "unmapped"
            d["status"] = "unmapped"
        directives.append(d)
    return directives


def write_report(out_dir: Path | None = None) -> dict:
    out_dir = out_dir or (config.BUILD_DIR / "reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    directives = build_directives()

    json_path = out_dir / "calibration.json"
    json_path.write_text(json.dumps(directives, indent=2, ensure_ascii=False), encoding="utf-8")

    md = ["# SV calibration directives", "",
          "_Synthetic ≠ evidence — these values shape generation only._", ""]
    for d in directives:
        md.append(f"## {d['condition']} (`{d['key']}`)")
        md.append(f"- target: **{d['target']} {d['unit']}** "
                  f"(p≈{d['target_probability']}), sex={d['sex']}, age {d['age_range']}")
        md.append(f"- source: {d['source']} · confidence: **{d['confidence']}**")
        md.append(f"- applies to: `{d['applies_to']}`")
        if "authored_value" in d:
            md.append(f"- authored value: `{d['authored_value']}`")
        md.append(f"- status: {d['status']}")
        if d["notes"]:
            md.append(f"- notes: {d['notes']}")
        md.append("")
    md_path = out_dir / "calibration.md"
    md_path.write_text("\n".join(md), encoding="utf-8")

    review = [d for d in directives if str(d["status"]).startswith("REVIEW")]
    return {"json": str(json_path), "md": str(md_path),
            "directives": len(directives), "needs_review": len(review)}
