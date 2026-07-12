"""Conversion-validation gate — DQD / Achilles in miniature.

Runs on *every* OMOP load (synthetic and, later, real). It is the gate the napkin
plan demands: record counts, vocabulary coverage (the real-work metric), and basic
referential integrity / plausibility. Not a replacement for the full OHDSI
DataQualityDashboard + Achilles — it is the always-on smoke test that fails fast and
surfaces the unmapped-code rate as a first-class number.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..omop import schema

CLINICAL_TABLES = schema.CLINICAL_EVENT_TABLES

# Tables whose rows carry a *_concept_id we expect to map to a standard concept.
_CONCEPT_COLS = {
    "condition_occurrence": "condition_concept_id",
    "drug_exposure": "drug_concept_id",
    "measurement": "measurement_concept_id",
}


@dataclass
class QualityReport:
    counts: dict[str, int]
    vocab_coverage: dict[str, float]      # table -> fraction of rows with concept_id != 0
    checks: list[tuple[str, bool, str]] = field(default_factory=list)  # (name, passed, detail)

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.checks.append((name, ok, detail))

    def __str__(self) -> str:
        lines = ["Quality gate " + ("PASS" if self.passed else "FAIL")]
        lines.append("  counts: " + ", ".join(f"{t}={n}" for t, n in self.counts.items()))
        if self.vocab_coverage:
            lines.append("  vocab coverage (standard-mapped): " +
                         ", ".join(f"{t}={c:.0%}" for t, c in self.vocab_coverage.items()))
        for name, ok, detail in self.checks:
            mark = "✓" if ok else "✗"
            lines.append(f"  {mark} {name}{(' — ' + detail) if detail else ''}")
        return "\n".join(lines)


def run_quality_gate(db_path) -> QualityReport:
    con = schema.connect(db_path)
    try:
        counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                  for t in CLINICAL_TABLES}

        coverage = {}
        for table, col in _CONCEPT_COLS.items():
            n = counts.get(table, 0)
            if n:
                mapped = con.execute(
                    f"SELECT count(*) FROM {table} WHERE {col} <> 0").fetchone()[0]
                coverage[table] = mapped / n

        report = QualityReport(counts=counts, vocab_coverage=coverage)

        # --- Plausibility / completeness ----------------------------------
        report.add("person table non-empty", counts["person"] > 0,
                   f"{counts['person']} persons")

        # Referential integrity: every clinical-event person_id exists in person.
        orphans = 0
        for t in ("visit_occurrence", "condition_occurrence", "drug_exposure", "measurement"):
            if counts.get(t):
                orphans += con.execute(
                    f"SELECT count(*) FROM {t} e "
                    f"LEFT JOIN person p ON p.person_id = e.person_id "
                    f"WHERE p.person_id IS NULL").fetchone()[0]
        report.add("no orphan clinical rows", orphans == 0, f"{orphans} orphans")

        # Every person has exactly one observation period.
        no_obs = con.execute(
            "SELECT count(*) FROM person p LEFT JOIN observation_period o "
            "ON o.person_id = p.person_id WHERE o.person_id IS NULL").fetchone()[0]
        report.add("every person has an observation_period", no_obs == 0,
                   f"{no_obs} without")

        # Birth-year plausibility.
        bad_yob = con.execute(
            "SELECT count(*) FROM person WHERE year_of_birth < 1900 "
            "OR year_of_birth > EXTRACT(YEAR FROM CURRENT_DATE)").fetchone()[0]
        report.add("plausible year_of_birth", bad_yob == 0, f"{bad_yob} implausible")

        # Gender mapped to a standard concept.
        bad_gender = con.execute(
            "SELECT count(*) FROM person WHERE gender_concept_id = 0").fetchone()[0]
        report.add("gender mapped", bad_gender == 0, f"{bad_gender} unmapped")

        return report
    finally:
        con.close()
