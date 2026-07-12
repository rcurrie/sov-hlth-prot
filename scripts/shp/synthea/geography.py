"""Build Synthea geography inputs for El Salvador from the persona spine + census.

Outputs two files in Synthea's *exact* native schema, so a stock Synthea build
can consume them via synthea.properties overrides:

  build/synthea/geography/sv_demographics.csv   (Synthea demographics.csv schema)
  build/synthea/geography/sv_zipcodes.csv       (Synthea zipcodes.csv schema)

Division of labour (documented in docs/data-sources.md):
  - Nemotron personas  -> municipality list, sex ratio, education mix, urban
                          share, and population apportionment within a department.
  - 2024 census        -> department totals, urban %, and the age pyramid.
  - SES proxy          -> income brackets (no direct income in either source).

Caveat: Synthea's race taxonomy (WHITE/HISPANIC/BLACK/...) is a US construct and
a poor fit for El Salvador (overwhelmingly mestizo). We set HISPANIC=1.0 and flag
this as a locale-mismatch — the same class of problem as ICD-11->OMOP downstream.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from . import config, personas

# Synthea demographics.csv columns (fetched from synthetichealth/synthea master).
DEMOGRAPHICS_HEADER = [
    "ID", "COUNTY", "NAME", "STNAME", "POPESTIMATE2015", "CTYNAME",
    "TOT_POP", "TOT_MALE", "TOT_FEMALE",
    "WHITE", "HISPANIC", "BLACK", "ASIAN", "NATIVE", "OTHER",
    # 18 five-year age bands (1=0-4 ... 18=85+) as overall proportions
    *[str(i) for i in range(1, 19)],
    # income brackets ($000/yr) as proportions
    "00..10", "10..15", "15..25", "25..35", "35..50", "50..75",
    "75..100", "100..150", "150..200", "200..999",
    # education as proportions
    "LESS_THAN_HS", "HS_DEGREE", "SOME_COLLEGE", "BS_DEGREE",
]

ZIPCODES_HEADER = ["", "USPS", "ST", "NAME", "ZCTA5", "LAT", "LON"]

# persona education_level -> Synthea education bucket
EDU_MAP = {
    "ninguno": "LESS_THAN_HS",
    "primaria": "LESS_THAN_HS",
    "secundaria": "LESS_THAN_HS",
    "bachillerato": "HS_DEGREE",
    "tecnico": "SOME_COLLEGE",
    "universitario": "BS_DEGREE",
    "posgrado": "BS_DEGREE",
}
EDU_BUCKETS = ["LESS_THAN_HS", "HS_DEGREE", "SOME_COLLEGE", "BS_DEGREE"]
SEX_MAP = {"Masculino": "M", "Femenino": "F"}

# Coarse income distribution (proportions over the 10 Synthea brackets) by
# education bucket. SES proxy only — El Salvador household incomes skew low
# (GDP/capita ~USD 5k). Brackets are $000/yr. Order matches the header.
INCOME_BRACKETS = ["00..10", "10..15", "15..25", "25..35", "35..50",
                   "50..75", "75..100", "100..150", "150..200", "200..999"]
INCOME_BY_EDU = {
    "LESS_THAN_HS": [0.55, 0.25, 0.12, 0.05, 0.02, 0.01, 0.0, 0.0, 0.0, 0.0],
    "HS_DEGREE":    [0.35, 0.28, 0.20, 0.10, 0.05, 0.02, 0.0, 0.0, 0.0, 0.0],
    "SOME_COLLEGE": [0.22, 0.25, 0.25, 0.15, 0.08, 0.04, 0.01, 0.0, 0.0, 0.0],
    "BS_DEGREE":    [0.10, 0.15, 0.25, 0.22, 0.15, 0.09, 0.03, 0.01, 0.0, 0.0],
}


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _census_departments() -> dict[str, dict]:
    out = {}
    for r in _read_csv(config.CENSUS_DIR / "sv_departments_2024.csv"):
        out[r["department"]] = {"population": int(r["population"]),
                                "pct_urban": float(r["pct_urban"])}
    return out


def _centroids() -> dict[str, tuple[float, float]]:
    return {r["department"]: (float(r["lat"]), float(r["lon"]))
            for r in _read_csv(config.CENSUS_DIR / "sv_department_centroids.csv")}


def _age_band_18() -> list[float]:
    """Expand the 6-band census pyramid (summed over sex) into Synthea's 18
    five-year bands. Even split within each broad band; documented approximation."""
    pyr = defaultdict(float)
    for r in _read_csv(config.CENSUS_DIR / "sv_age_pyramid_2024.csv"):
        pyr[r["age_band"]] += float(r["fraction"])
    # weights mapping broad band -> list of (synthea_band_index, weight)
    spread = {
        "0-17":  [(1, 5), (2, 5), (3, 5), (4, 3)],
        "18-29": [(4, 2), (5, 5), (6, 5)],
        "30-44": [(7, 1), (8, 1), (9, 1)],
        "45-59": [(10, 1), (11, 1), (12, 1)],
        "60-74": [(13, 1), (14, 1), (15, 1)],
        "75+":   [(16, 5), (17, 3), (18, 2)],
    }
    bands = [0.0] * 19  # 1-indexed
    for broad, frac in pyr.items():
        weights = spread[broad]
        wsum = sum(w for _, w in weights)
        for idx, w in weights:
            bands[idx] += frac * w / wsum
    total = sum(bands)
    return [bands[i] / total for i in range(1, 19)]


PROVIDER_HEADER = [
    "provider_num", "npi", "name", "address", "city", "state", "zip",
    "fips_county", "lat", "lon", "phone", "provider_type_code", "category",
    "emergency", "upin", "pin", "region_code", "bed_count", "clia_lab_number",
]


def build_providers(out_dir: Path | None = None) -> dict:
    """Author minimal SV provider files: one hospital + one primary-care facility
    per department, placed at the department centroid. Synthea assigns each
    patient the nearest provider; without these, every patient fails with a null
    provider. `state` must equal the generation state ("El Salvador")."""
    out_dir = out_dir or (config.BUILD_DIR / "synthea" / "providers")
    out_dir.mkdir(parents=True, exist_ok=True)
    centroids = _centroids()

    hospitals, primary = [], []
    pnum = 900000
    for i, dep in enumerate(config.DEPARTMENTS):
        lat, lon = centroids.get(dep, (13.7, -89.2))
        npi = f"9{(100000000 + i):09d}"[:10]
        base = {
            "address": "", "city": dep, "state": "El Salvador", "zip": "",
            "fips_county": "", "lat": lat, "lon": lon, "phone": "",
            "upin": "", "pin": "", "region_code": "", "clia_lab_number": "",
        }
        hospitals.append({**base, "provider_num": pnum, "npi": npi,
                          "name": f"Hospital Nacional de {dep}",
                          "provider_type_code": "00-09", "category": "01-02",
                          "emergency": "true", "bed_count": 120})
        pnum += 1
        primary.append({**base, "provider_num": pnum, "npi": f"8{(100000000 + i):09d}"[:10],
                        "name": f"Unidad de Salud {dep}",
                        "provider_type_code": "00-04", "category": "21-01",
                        "emergency": "false", "bed_count": ""})
        pnum += 1

    def _write(path, rows):
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=PROVIDER_HEADER)
            w.writeheader()
            w.writerows(rows)

    _write(out_dir / "sv_hospitals.csv", hospitals)
    _write(out_dir / "sv_primary_care.csv", primary)
    return {"hospitals": len(hospitals), "primary_care": len(primary),
            "dir": str(out_dir)}


def build(out_dir: Path | None = None, *, max_shards=None, local_dir=None) -> dict:
    """Generate sv_demographics.csv and sv_zipcodes.csv. Returns a summary dict."""
    out_dir = out_dir or (config.BUILD_DIR / "synthea" / "geography")
    out_dir.mkdir(parents=True, exist_ok=True)

    census = _census_departments()
    centroids = _centroids()
    age18 = _age_band_18()
    detail = personas.municipality_detail(max_shards=max_shards, local_dir=local_dir)

    # aggregate per (department, municipality)
    muni: dict[tuple[str, str], dict] = {}
    for row in detail:
        dep, mun = row["department"], row["municipality"]
        key = (dep, mun)
        m = muni.setdefault(key, {
            "n": 0, "n_male": 0, "n_female": 0, "n_urban": 0,
            "edu": dict.fromkeys(EDU_BUCKETS, 0),
        })
        n = row["n"]
        m["n"] += n
        if SEX_MAP.get(row["sex"]) == "M":
            m["n_male"] += n
        elif SEX_MAP.get(row["sex"]) == "F":
            m["n_female"] += n
        if row["area"] == "urbano":
            m["n_urban"] += n
        m["edu"][EDU_MAP.get(row["education_level"], "LESS_THAN_HS")] += n

    # department-level persona totals for apportionment
    dep_persona_total: dict[str, int] = defaultdict(int)
    for (dep, _mun), m in muni.items():
        dep_persona_total[dep] += m["n"]

    demo_rows, zip_rows = [], []
    next_id = 35000
    for (dep, mun), m in sorted(muni.items()):
        if dep not in census:
            continue
        dep_pop = census[dep]["population"]
        share = m["n"] / dep_persona_total[dep] if dep_persona_total[dep] else 0
        tot_pop = max(1, round(dep_pop * share))

        sex_n = m["n_male"] + m["n_female"]
        male_frac = (m["n_male"] / sex_n) if sex_n else 0.5
        female_frac = 1.0 - male_frac

        edu_total = sum(m["edu"].values()) or 1
        edu_frac = {b: m["edu"][b] / edu_total for b in EDU_BUCKETS}

        # income = education-weighted SES proxy
        income = [0.0] * len(INCOME_BRACKETS)
        for b in EDU_BUCKETS:
            w = edu_frac[b]
            for i, v in enumerate(INCOME_BY_EDU[b]):
                income[i] += w * v
        isum = sum(income) or 1
        income = [x / isum for x in income]

        lat, lon = centroids.get(dep, (13.7, -89.2))

        row = {
            "ID": next_id, "COUNTY": dep, "NAME": mun, "STNAME": "El Salvador",
            "POPESTIMATE2015": tot_pop, "CTYNAME": dep,
            "TOT_POP": tot_pop,
            "TOT_MALE": round(male_frac, 6), "TOT_FEMALE": round(female_frac, 6),
            "WHITE": 0.0, "HISPANIC": 1.0, "BLACK": 0.0, "ASIAN": 0.0,
            "NATIVE": 0.0, "OTHER": 0.0,
        }
        for i in range(18):
            row[str(i + 1)] = round(age18[i], 6)
        for i, bracket in enumerate(INCOME_BRACKETS):
            row[bracket] = round(income[i], 6)
        for b in EDU_BUCKETS:
            row[b] = round(edu_frac[b], 6)
        demo_rows.append(row)

        zip_rows.append({"": "", "USPS": "El Salvador", "ST": "SV",
                         "NAME": mun, "ZCTA5": "", "LAT": lat, "LON": lon})
        next_id += 1

    demo_path = out_dir / "sv_demographics.csv"
    with demo_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=DEMOGRAPHICS_HEADER)
        w.writeheader()
        w.writerows(demo_rows)

    zip_path = out_dir / "sv_zipcodes.csv"
    with zip_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ZIPCODES_HEADER)
        w.writeheader()
        w.writerows(zip_rows)

    providers = build_providers()

    return {
        "demographics_csv": str(demo_path),
        "zipcodes_csv": str(zip_path),
        "municipalities": len(demo_rows),
        "departments": len({r["COUNTY"] for r in demo_rows}),
        "total_population": sum(r["TOT_POP"] for r in demo_rows),
        "providers": providers,
    }
