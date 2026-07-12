"""Load the Nemotron-Personas-El-Salvador spine and sample a seed population.

The dataset is 148k synthetic Salvadoran personas (CC BY 4.0). We read it
remotely with DuckDB, which pushes column/row projection down to the parquet
files over HTTP range requests — so pulling the ~10 demographic columns costs
a few seconds, not the full ~570 MB download.

Personas are *working adults*; their age distribution skews adult. They supply
the adult demographic JOINTS (age × sex × education × occupation × department).
The full population age pyramid is layered on from census (see geography.py).
"""
from __future__ import annotations

import functools
from typing import Optional

from . import config


@functools.lru_cache(maxsize=1)
def _con():
    import duckdb

    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    return con


def _shard_urls(max_shards: Optional[int] = None) -> list[str]:
    shards = config.PERSONA_SHARDS[: max_shards or len(config.PERSONA_SHARDS)]
    return [f"{config.HF_PARQUET_BASE}/{s}" for s in shards]


def _source_list(local_dir, max_shards):
    """Prefer cached local parquet shards; otherwise stream from HuggingFace."""
    local_dir = local_dir or config.PERSONAS_DIR
    local = sorted(local_dir.glob("*.parquet"))
    if local:
        urls = [str(p) for p in local]
        return urls[: max_shards or len(urls)]
    return _shard_urls(max_shards)


def _sql_list(urls: list[str]) -> str:
    inner = ", ".join("'" + u.replace("'", "''") + "'" for u in urls)
    return f"read_parquet([{inner}])"


def spine_columns_sql() -> str:
    return ", ".join(config.SPINE_COLUMNS + config.NARRATIVE_COLUMNS)


def sample(n: int, seed: int = 1, *, max_shards: Optional[int] = None, local_dir=None):
    """Return `n` personas (spine + narrative columns) as a list of dicts.

    Deterministic given (n, seed): DuckDB's `setseed` + `random()` ordering.
    """
    con = _con()
    src = _sql_list(_source_list(local_dir, max_shards))
    con.execute(f"SELECT setseed({(seed % 1000) / 1000.0})")
    rows = con.execute(
        f"SELECT {spine_columns_sql()} FROM {src} "
        f"ORDER BY random() LIMIT {int(n)}"
    ).fetchall()
    cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in rows]


def joint_distribution(*, max_shards: Optional[int] = None, local_dir=None):
    """Aggregate the spine into the age×sex×education×area×department joints.

    Returns rows: (department, area, sex, age_band, education_level, n).
    This is what we fold into the Synthea demographics CSV so the synthetic
    population's adult marginals track the Nemotron spine.
    """
    con = _con()
    src = _sql_list(_source_list(local_dir, max_shards))
    return con.execute(
        f"""
        SELECT department, area, sex,
               CASE
                 WHEN age < 18 THEN '0-17'
                 WHEN age < 30 THEN '18-29'
                 WHEN age < 45 THEN '30-44'
                 WHEN age < 60 THEN '45-59'
                 WHEN age < 75 THEN '60-74'
                 ELSE '75+'
               END AS age_band,
               education_level,
               count(*) AS n
        FROM {src}
        GROUP BY ALL
        ORDER BY department, area, sex, age_band, education_level
        """
    ).fetchall()


def municipality_detail(*, max_shards: Optional[int] = None, local_dir=None):
    """Per (department, municipality, area, sex, education_level) persona counts.

    Used by geography.py to apportion department population across municipalities
    and to derive per-municipality sex / education / urban mixes.
    """
    con = _con()
    src = _sql_list(_source_list(local_dir, max_shards))
    rows = con.execute(
        f"""
        SELECT department, municipality, area, sex, education_level, count(*) AS n
        FROM {src}
        WHERE municipality IS NOT NULL AND department IS NOT NULL
        GROUP BY ALL
        """
    ).fetchall()
    cols = [d[0] for d in con.description]
    return [dict(zip(cols, r)) for r in rows]


def department_summary(*, max_shards: Optional[int] = None, local_dir=None):
    """(department, n, pct_urban, mean_age) — quick sanity / calibration view."""
    con = _con()
    src = _sql_list(_source_list(local_dir, max_shards))
    return con.execute(
        f"""
        SELECT department,
               count(*) AS n,
               round(100.0 * avg(CASE WHEN area = 'urbano' THEN 1 ELSE 0 END), 1) AS pct_urban,
               round(avg(age), 1) AS mean_age
        FROM {src}
        GROUP BY department
        ORDER BY n DESC
        """
    ).fetchall()
