# The Sovereign Health Protocol (SHP)

The Sovereign Health Protocol (SHP) helps a country turn the health records it *already has*
into trustworthy answers to real public-health questions — which treatments work, where an
outbreak is spreading, whether a chronic-disease program is actually helping — **without
patient records ever leaving the country**. It reads the standard format hospitals already
export ([FHIR](https://hl7.org/fhir/)) and converts it into a common research format
([OMOP](https://www.ohdsi.org/data-standardization/)) that ministries of health, universities,
and funders worldwide already trust. This is not theoretical: the same open analytics toolkit
SHP builds on ([OHDSI's HADES R packages](https://ohdsi.github.io/Hades/), [peer-reviewed](https://pmc.ncbi.nlm.nih.gov/articles/PMC10868467/))
has produced published evidence at scale — for example the [LEGEND-HTN study in *The
Lancet*](https://www.thelancet.com/article/S0140-6736(19)32317-7/fulltext), a **multinational**
analysis comparing first-line blood-pressure treatments across ~5 million patients and nine
databases, each analyzed *in place* with only results shared. Because every study is expressed
against one open, well-documented standard (the [*Book of
OHDSI*](https://ohdsi.github.io/TheBookOfOhdsi/)), El Salvador can join — and help lead —
regional evidence networks across the Americas, collaborating with **WHO / PAHO** and
international partners on equal footing while its citizens' data stays home. Everything in this
repository first runs on realistic **synthetic** patients — invented records, never real
people — so the methods are proven safe *before* they ever touch a real record. And because
that synthetic path is fully open and reproducible, it doubles as a **training ground for
homegrown health-informatics expertise**, extending El Salvador's substantial national
investment in AI and engineering education into public health. (This project's synthetic
population is itself generated from NVIDIA's
[Nemotron-Personas-El-Salvador](https://huggingface.co/datasets/nvidia/Nemotron-Personas-El-Salvador)
dataset — an explicitly *Sovereign AI* resource grounded in El Salvador's 2024 national census.)

## Just want to try the notebooks? (start here)

No install, no download — open in Colab, then **Runtime ▸ Change runtime type ▸ R**, then Run all:

- **OMOP population explorer** — cohort characterization across the synthetic population
  [→ open in Colab](https://colab.research.google.com/github/rcurrie/sov-hlth-prot/blob/main/notebooks/sv_omop_explorer.ipynb)
- **FHIR single-patient view** — one patient's raw FHIR R4 bundle
  [→ open in Colab](https://colab.research.google.com/github/rcurrie/sov-hlth-prot/blob/main/notebooks/sv_fhir_patient.ipynb)

Each notebook's `DATA_URL` is pre-wired to this repo's sample files
([`OMOP/sv_sample100.duckdb`](OMOP/sv_sample100.duckdb),
[`FHIR/sample_patient_fhir.json`](FHIR/sample_patient_fhir.json)), so they fetch their own
data automatically on Colab. **Send a researcher either Colab link and they're running in
~1 minute.**

> The FHIR patient (*Cyndy Ji Monahan*) is the **same person** as OMOP `person_id = 21` —
> their HbA1c / eGFR curves match across the two views.


## Note for IRBs
Everything in this repository is **synthetic** — patients generated algorithmically to match
population-level statistics, with **no real records and no protected health information (PHI)**,
involving **no human subjects and no identifiable private information**; nothing here can be
traced to, or used to re-identify, any real person. That is by design: SHP is built as a
**privacy-preserving, minimal-risk architecture**, and this synthetic **staging path** exists
precisely so that analytic methods can be fully pre-specified, reviewed, and validated *before*
any real data is involved. The production path is **federated and de-identified**: records are
de-identified inside the source health system's own secure environment, analyses run against the
standardized [OMOP](https://www.ohdsi.org/data-standardization/) model *in place*, and **only
aggregate, non-identifiable results ever leave it** — patient-level data never crosses
institutional or national borders, and standardizing on [OMOP/OHDSI](https://www.ohdsi.org/methods-demo/)
keeps each study transparent, pre-specifiable, and reproducible for review. We anticipate and
welcome IRB oversight as an explicit gate: **no real-world data is accessed until the production
protocol receives its own IRB approval** — this repository covers only the synthetic staging that
precedes that step.

## Architecture and Data Flow

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/data-flow-dark.svg">
  <img alt="Sovereign Health Protocol data-flow: a twin-path FHIR to OMOP to OHDSI pipeline inside a sovereign boundary on in-country compute, with an external partner (PAHO, WHO, or the OHDSI network) bringing standardized surveillance packages in and only aggregated findings out." src="docs/data-flow.svg" width="100%">
</picture>

*Twin-path FHIR → OMOP → OHDSI on in-country compute. The only things that cross the
sovereign boundary are the zero-PHI **synthetic corpus** (out) and a partner's standardized
**surveillance packages** (in) / **aggregated findings** (out) — raw patient data never
crosses. Full design in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).*

⚠️ This repository is SHP's **synthetic staging path** — the open, zero-PHI playground where
the analytics are built and validated (against a known answer key) before the production path
runs the identical workflows on sovereign, de-identified data. It is a **proof of concept**:
the OMOP conversion and estimator stack run end-to-end today; full production vocabulary
mapping (OHDSI Athena) is the required next step, lightly simulated here (see below).*

## Why this is built the way it is

**Standardized on OMOP + OHDSI, by design.** By adopting the **OMOP Common Data Model** and
the **OHDSI** analytical stack, every study here is expressed in the same standardized,
transparent, mathematically reproducible form that international funders and regulators
(State Department, CDC, USAID, and the global research community) expect. Methodology is a
shared language, not a bespoke black box.

**Sovereignty through federation.** OMOP enables a **federated network model**: El Salvador
can run internationally validated analytical *packages* locally, on its own secure
infrastructure. Raw, patient-level records never cross national borders — only aggregated,
non-identifiable statistical findings are shared. The synthetic corpus is the one artifact
that *can* cross the boundary (it contains no PHI) and is **regionally exportable** as the
platform expands across Central and South America.

**A foundation for regional leadership.** Standardized, verifiable observational insight is
the substrate for El Salvador to grow homegrown biomedical-data-science capacity — training
in-country engineers and analysts on the same tooling the rest of the OHDSI world uses.
*(Forward-looking: high-fidelity, verifiable public-health outcomes are also the kind of
signal a future "health-token" incentive layer — tokenizing verified outcomes, data-sharing
compliance, or intervention milestones — could one day be built on. That is exploratory
vision, not a current feature.)*

See **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the full twin-path design.

### Twin-path deployment

Both paths run **identical** analytical logic — build and validate once, run anywhere. SHP
is **health-system-agnostic**: the only requirement is a standard **FHIR R4 export**, so any
FHIR-native health system can feed the production path.

- **Synthetic staging path (this repo, today).** High-fidelity synthetic populations via
  Synthea → standard FHIR R4 → OMOP → causal estimators validated against an injected,
  known treatment effect. Safe to share, safe to iterate.
- **Production path (future).** De-identified FHIR exported from a sovereign health cloud —
  for example, El Salvador's **DoctorSV** telemedicine platform — via a service such as the
  **Google Cloud Healthcare API** → BigQuery → the *same* OMOP tables and the *same*
  notebooks, with no structural code change. The synthetic path exists to de-risk this one.
  
## Repository layout

```
sov-hlth-prot/
├── notebooks/               # the two R notebooks (source of truth)
├── OMOP/  sv_sample100.duckdb        ✅ checked in — 100-person OMOP subset (~4.5 MB)
├── FHIR/  sample_patient_fhir.json   ✅ checked in — one curated FHIR R4 bundle (~6 MB)
├── config/                  # Synthea SV overrides: synthea.properties + payers/
├── modules/                 # custom Synthea disease modules: dengue, CKDu
├── reference/               # checked-in inputs: census/, burden/, vocab/ (starter crosswalk)
├── scripts/shp/        # the Python machinery (one installable package)
│   ├── synthea/   personas (Nemotron) + geography + generate + modules
│   ├── omop/      DDL, schema, vocabulary (starter layer + crosswalk seam), ETL
│   ├── estimators/ ate (naive/IPTW/AIPW/TMLE) + diagnostics
│   ├── study/     diabetes semi-synthetic answer-key (dgp → omop → cohort → estimate)
│   ├── quality/   DQD/Achilles-lite gate — reports vocabulary coverage as a metric
│   └── samples.py rebuild the checked-in OMOP/ + FHIR/ samples
├── docs/ARCHITECTURE.md     # twin-path design + the production migration path
├── tests/                   # ETL + estimator + round-trip + geography/module tests
├── pyproject.toml           # one venv, deps below; installs the `shp` CLI
└── data/                    ❌ git-ignored — all reproducible/downloaded artifacts
```

Everything under `data/` is **rebuilt locally** from the steps below and is never committed
(the Synthea fat-jar ~190 MB, the Nemotron parquet cache, the full FHIR/CSV output, the
full-corpus OMOP db). The small samples in `OMOP/` and `FHIR/` are the only data in git.

## Requirements

| Need | Version / note |
|---|---|
| **Python** | 3.11+ (**3.12 recommended** for the scientific stack). |
| [**uv**](https://docs.astral.sh/uv/) | manages the Python venv. |
| **Java (JDK/JRE 17+)** | only to *generate* fresh Synthea data. Verified on JDK 17–26. On macOS: `brew install openjdk` (keg-only path is auto-discovered). |
| **R 4.x** | only to *run the notebooks locally* (Colab needs none of this). Plus JupyterLab from the `notebooks` extra. |
| **Network** | HuggingFace (Nemotron parquet, streamed) + GitHub (Synthea fat-jar) — only for the Synthea generation step. |

Python deps: `duckdb`, `numpy`, `pandas`, `scipy`, `scikit-learn`, `pyyaml` (+ `pytest` dev).

## Reproduce everything locally

```bash
uv venv --python python3.12
uv pip install -e ".[dev]"
pytest                                   # ~sanity: ETL + estimators + round-trip, no Java
```

### 1 · Generate the SV synthetic corpus (needs Java 17+)

```bash
shp synthea bootstrap               # download Synthea fat-jar → data/vendor/ (~190 MB)
shp synthea generate -p 1000 --seed 1
# → FHIR R4 + CSV + Spanish narratives under data/build/run/output/{fhir,csv}
```

Other SV pipeline steps: `shp synthea status | personas | geography | calibrate |
validate | narratives`. See `shp synthea -h`. (`synthea validate` needs no Java.)

### 2 · Convert to OMOP + check quality (with the vocabulary seam)

```bash
shp etl                             # baseline: source codes load unmapped (concept_id = 0)
shp etl --vocab                     # apply the starter crosswalk → standard concept_ids
shp quality data/omop/sv.duckdb     # counts, referential integrity, and vocab coverage %
```

The starter crosswalk ([`reference/vocab/starter_crosswalk.csv`](reference/vocab/starter_crosswalk.csv))
maps the codes we've validated (Type 2 diabetes, HbA1c) to real standard concepts and lists
the rest as explicit Athena/Usagi TODOs. Coverage is a **measured number**, not a hidden
assumption — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#the-vocabulary-mapping-seam).

### 3 · Run the causal answer-key study (no Java needed)

```bash
shp study diabetes
# authors a known treatment effect, writes it to OMOP, rebuilds the analytic frame
# from CDM by SQL, then recovers it:  naive (biased) → IPTW → AIPW → TMLE
```

### 4 · Regenerate the checked-in Colab samples (optional)

```bash
shp build-samples                   # OMOP/sv_sample100.duckdb + FHIR/sample_patient_fhir.json
```

## Run the notebooks locally (R kernel)

Colab needs none of this; only for editing/running on your own machine.

```bash
# Python side — JupyterLab (uv, into the same venv)
uv pip install -e ".[notebooks]"

# R side — packages + register the Jupyter R kernel
Rscript -e 'install.packages(c("DBI","duckdb","dplyr","tidyr","ggplot2","jsonlite","IRkernel"),
                             repos="https://cloud.r-project.org")'
Rscript -e 'IRkernel::installspec(user = TRUE, name = "ir", displayname = "R")'

# launch
.venv/bin/jupyter lab --notebook-dir=notebooks
```

Open either notebook, pick the **R** kernel, Run all. Each auto-discovers its data file in
`OMOP/` / `FHIR/`. Point the OMOP notebook at the full corpus with
`Sys.setenv(SV_OMOP_DB = "data/omop/sv.duckdb")` before the connect cell.

**Headless validation** (expect 0 errors):
```bash
.venv/bin/jupyter nbconvert --to notebook --execute \
  --ExecutePreprocessor.kernel_name=ir --output _check.ipynb notebooks/sv_omop_explorer.ipynb
```

## Honest limits

- **Synthetic ≠ evidence.** The study validates *estimators* — you only recover the
  structure you inject. Never a clinical or epidemiological claim.
- **A full OHDSI Athena vocabulary build is the required production step — this repo only
  simulates it.** As a proof of concept, codes map to standard `concept_id`s only where
  we've validated them (via the crosswalk seam); the rest stay `concept_id = 0` and are
  *reported* as coverage. Real, complete mapping needs the Athena build (licence-gated,
  multi-GB) — it can't ship in the repo or Colab, so it lives on the production path. See
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **ICD-11 → SNOMED is the known weak spot** and belongs to the *production* feed (a source
  system may emit ICD-11; Synthea emits SNOMED). Bridged via ICD-10→SNOMED + Usagi.
- **13-table OMOP subset** and a **DuckDB single file** — a portable sandbox, not a full
  OHDSI Postgres + Atlas/WebAPI stack. Columns follow the v5.4 spec so records port.
- **Descriptive notebooks only** — treatment arms in raw synthetic data are too thin for a
  valid comparative-effectiveness estimate; the causal answer-key lives in `study/`.

*License: Apache-2.0. Everything in this repository is synthetic and contains zero PHI.*
