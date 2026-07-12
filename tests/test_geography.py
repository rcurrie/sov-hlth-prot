from shp.synthea import geography


def test_build_geography_schema_and_sums(tmp_path, persona_dir):
    out = tmp_path / "geo"
    summary = geography.build(out_dir=out, local_dir=persona_dir)

    assert summary["municipalities"] >= 5
    assert summary["total_population"] > 0

    import csv
    with (out / "sv_demographics.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        header = rows[0].keys()

    # exact Synthea schema present
    assert set(geography.DEMOGRAPHICS_HEADER) == set(header)

    for r in rows:
        age = sum(float(r[str(i)]) for i in range(1, 19))
        assert abs(age - 1.0) < 1e-3, f"age bands sum {age}"
        edu = sum(float(r[b]) for b in geography.EDU_BUCKETS)
        assert abs(edu - 1.0) < 1e-3, f"education sums {edu}"
        income = sum(float(r[b]) for b in geography.INCOME_BRACKETS)
        assert abs(income - 1.0) < 1e-3, f"income sums {income}"
        assert abs(float(r["TOT_MALE"]) + float(r["TOT_FEMALE"]) - 1.0) < 1e-3
        assert float(r["HISPANIC"]) == 1.0


def test_zipcodes_schema(tmp_path, persona_dir):
    out = tmp_path / "geo"
    geography.build(out_dir=out, local_dir=persona_dir)
    import csv
    with (out / "sv_zipcodes.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows
    assert {"USPS", "ST", "NAME", "LAT", "LON"} <= set(rows[0].keys())
    assert all(r["ST"] == "SV" for r in rows)
