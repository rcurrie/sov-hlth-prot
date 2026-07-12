"""Spanish-language (Salvadoran) clinical narratives.

Two layers:
  - social context: reuses the Nemotron persona's own Spanish prose (it is already
    Salvadoran Spanish, CC BY 4.0) plus a templated demographic line from the spine.
  - clinical summary: templates a Spanish summary from the patient's conditions.

Standalone (`generate_sample`) emits social/demographic narratives only — zero
clinical claims, zero PHI. After a real Synthea run, `from_synthea_output` joins
patients.csv + conditions.csv to produce full clinical narratives per patient.

Deterministic templates by default (no LLM dependency); an LLM polish step can be
layered later behind the same interface.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from . import config, personas

SEX_ES = {"Masculino": "masculino", "Femenino": "femenino"}
AREA_ES = {"urbano": "zona urbana", "rural": "zona rural"}

# SNOMED code -> Salvadoran-Spanish clinical display
CONDITION_ES = {
    "38362002": "dengue",
    "409708008": "dengue grave (fiebre hemorrágica)",
    "709044004": "enfermedad renal crónica de etiología no tradicional (nefropatía mesoamericana)",
    "46177005": "enfermedad renal crónica terminal",
    "44054006": "diabetes mellitus tipo 2",
    "59621000": "hipertensión arterial esencial",
}


def social_context(persona: dict) -> str:
    sexo = SEX_ES.get(persona.get("sex", ""), persona.get("sex", ""))
    line = f"Paciente {sexo} de {persona.get('age')} años"
    if persona.get("municipality"):
        line += f", residente en {persona['municipality']}"
    if persona.get("department"):
        line += f", departamento de {persona['department']}"
    area = AREA_ES.get(persona.get("area", ""), persona.get("area", ""))
    if area:
        line += f" ({area})"
    line += "."
    # Only render fields we actually have (the Synthea-output path lacks some).
    extras = []
    if persona.get("education_level"):
        extras.append(f"Nivel educativo: {persona['education_level']}")
    if persona.get("occupation"):
        extras.append(f"Ocupación: {persona['occupation']}")
    if persona.get("marital_status"):
        extras.append(f"Estado civil: {persona['marital_status']}")
    if persona.get("household_type"):
        extras.append(f"hogar {persona['household_type']}")
    if extras:
        line += " " + ". ".join(extras) + "."
    prose = persona.get("professional_persona") or persona.get("persona") or ""
    if prose:
        line += f"\n\nContexto social (persona sintética):\n{prose.strip()}"
    return line


def clinical_summary(conditions: list[dict]) -> str:
    if not conditions:
        return "Sin condiciones crónicas activas registradas en este corte."
    lines = ["Resumen clínico:"]
    for c in conditions:
        es = CONDITION_ES.get(str(c.get("code")), c.get("display", "condición"))
        start = c.get("start", "")
        when = f" (inicio {start})" if start else ""
        lines.append(f"  - {es}{when}")
    return "\n".join(lines)


def render(persona: dict, conditions: list[dict] | None = None) -> str:
    parts = [
        "# Resumen del paciente sintético",
        "",
        "> Datos 100% sintéticos · sin PHI · no constituyen evidencia clínica.",
        "",
        social_context(persona),
        "",
        clinical_summary(conditions or []),
    ]
    return "\n".join(parts)


def generate_sample(n: int = 25, seed: int = 1, out_dir: Path | None = None,
                    *, max_shards=None, local_dir=None) -> dict:
    """Emit N social/demographic ES narratives (no clinical content)."""
    out_dir = out_dir or (config.BUILD_DIR / "narratives")
    out_dir.mkdir(parents=True, exist_ok=True)
    people = personas.sample(n, seed=seed, max_shards=max_shards, local_dir=local_dir)
    written = []
    for p in people:
        text = render(p, conditions=None)
        fname = f"{p['uuid']}.md"
        (out_dir / fname).write_text(text, encoding="utf-8")
        written.append(fname)
    (out_dir / "index.json").write_text(
        json.dumps({"count": len(written), "seed": seed, "files": written},
                   indent=2, ensure_ascii=False), encoding="utf-8")
    return {"out_dir": str(out_dir), "count": len(written)}


def from_synthea_output(synthea_csv_dir: Path, out_dir: Path | None = None,
                        limit: int | None = None) -> dict:
    """Join Synthea patients.csv + conditions.csv into full clinical narratives.

    Used after a real Synthea run. Patient demographics come from Synthea's own
    output (already SV-localized via our geography), conditions from conditions.csv.
    """
    synthea_csv_dir = Path(synthea_csv_dir)
    out_dir = out_dir or (config.BUILD_DIR / "narratives_clinical")
    out_dir.mkdir(parents=True, exist_ok=True)

    patients = {}
    with (synthea_csv_dir / "patients.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            patients[r["Id"]] = r

    conds: dict[str, list[dict]] = {}
    with (synthea_csv_dir / "conditions.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            conds.setdefault(r["PATIENT"], []).append(
                {"code": r.get("CODE"), "display": r.get("DESCRIPTION"),
                 "start": r.get("START")})

    written = 0
    for pid, prow in patients.items():
        persona = {
            "sex": "Masculino" if prow.get("GENDER") == "M" else "Femenino",
            "age": _age(prow.get("BIRTHDATE"), prow.get("DEATHDATE")),
            "municipality": prow.get("CITY"),
            "department": prow.get("COUNTY"),
            "marital_status": prow.get("MARITAL", ""),
        }
        text = render(persona, conds.get(pid, []))
        (out_dir / f"{pid}.md").write_text(text, encoding="utf-8")
        written += 1
        if limit and written >= limit:
            break
    return {"out_dir": str(out_dir), "count": written}


def _age(birthdate: str | None, deathdate: str | None = None) -> str:
    """Age in years at death (if dead) or today, from ISO YYYY-MM-DD strings."""
    import datetime

    if not birthdate:
        return "?"
    try:
        born = datetime.date.fromisoformat(birthdate[:10])
        end = (datetime.date.fromisoformat(deathdate[:10])
               if deathdate else datetime.date.today())
        years = end.year - born.year - ((end.month, end.day) < (born.month, born.day))
        return str(max(0, years))
    except Exception:
        return "?"
