from shp.synthea import calibration


def test_directives_cover_burden():
    directives = calibration.build_directives()
    keys = {d["key"] for d in directives}
    assert {"dengue", "ckdu", "diabetes", "hypertension"} <= keys


def test_dengue_authored_matches_target():
    by = {(d["key"], d["sex"]): d for d in calibration.build_directives()}
    dengue = by[("dengue", "A")]
    # 900 per 100k/yr -> 0.009 annual probability, matching the module knob
    assert dengue["target_probability"] == 0.009
    assert dengue["authored_value"] == 0.009
    assert dengue["status"] == "ok"


def test_ckdu_sex_specific_knobs():
    by = {(d["key"], d["sex"]): d for d in calibration.build_directives()}
    assert by[("ckdu", "M")]["authored_value"] == 0.18
    assert by[("ckdu", "M")]["status"] == "ok"
    assert by[("ckdu", "F")]["authored_value"] == 0.04
    assert by[("ckdu", "F")]["status"] == "ok"


def test_no_authored_mismatch():
    review = [d for d in calibration.build_directives()
              if str(d["status"]).startswith("REVIEW")]
    assert review == [], f"unexpected authored/target mismatch: {review}"
