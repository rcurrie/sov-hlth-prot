"""Offline test fixtures: a tiny local persona parquet so tests need no network."""
import duckdb
import pytest

# A handful of synthetic persona rows spanning departments, sexes, education,
# urban/rural — enough to exercise geography/persona aggregation offline.
_ROWS = [
    # uuid, sex, age, marital, household, education, occupation, area, municipality, department
    ("u1", "Masculino", 34, "casado", "nuclear", "primaria", "Agricultura", "rural", "Tecoluca", "San Vicente"),
    ("u2", "Femenino", 41, "union_libre", "extendido", "bachillerato", "Comercio", "urbano", "Tecoluca", "San Vicente"),
    ("u3", "Masculino", 52, "casado", "nuclear", "ninguno", "Agricultura", "rural", "Zacatecoluca", "La Paz"),
    ("u4", "Femenino", 29, "soltero", "unipersonal", "universitario", "Salud", "urbano", "San Salvador Centro", "San Salvador"),
    ("u5", "Masculino", 60, "viudo", "monoparental", "secundaria", "Construcción", "urbano", "San Salvador Centro", "San Salvador"),
    ("u6", "Femenino", 37, "casado", "nuclear", "tecnico", "Educación", "urbano", "Santa Ana Centro", "Santa Ana"),
    ("u7", "Masculino", 45, "separado", "extendido", "primaria", "Pesca", "rural", "Usulután Norte", "Usulután"),
    ("u8", "Femenino", 23, "soltero", "nuclear", "posgrado", "Tecnología", "urbano", "San Salvador Centro", "San Salvador"),
]


@pytest.fixture(scope="session")
def persona_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("personas")
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE p (uuid VARCHAR, sex VARCHAR, age BIGINT, marital_status VARCHAR, "
        "household_type VARCHAR, education_level VARCHAR, occupation VARCHAR, area VARCHAR, "
        "municipality VARCHAR, department VARCHAR, country VARCHAR, persona VARCHAR, "
        "professional_persona VARCHAR, family_persona VARCHAR, cultural_background VARCHAR)"
    )
    for r in _ROWS:
        con.execute(
            "INSERT INTO p VALUES (?,?,?,?,?,?,?,?,?,?, 'El Salvador', ?, ?, '', '')",
            [*r, f"Persona de {r[8]}.", f"Trabaja en {r[6]}."],
        )
    out = str(d / "0000.parquet")
    con.execute(f"COPY p TO '{out}' (FORMAT parquet)")
    return d
