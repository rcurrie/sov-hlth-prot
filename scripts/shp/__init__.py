"""The Sovereign Health Protocol (SHP) — a zero-PHI synthetic El Salvador health-data sandbox.

The synthetic staging path of a sovereign FHIR → OMOP → OHDSI pipeline.
One repo, one venv, one CLI (``shp``) spanning three stages:

    synthea   Nemotron-Personas-El-Salvador -> SV-calibrated Synthea -> FHIR R4 + CSV
    omop      Synthea CSV -> OMOP CDM v5.4 (DuckDB) + a data-quality gate
    study     semi-synthetic causal answer-key (naive -> IPTW -> AIPW -> TMLE)

Everything here is synthetic. Synthetic != evidence: never an epidemiological claim.
"""
__version__ = "0.1.0"
