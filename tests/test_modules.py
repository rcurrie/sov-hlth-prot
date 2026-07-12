from shp.synthea import modules


def test_authored_modules_are_valid():
    results = modules.validate_all()
    assert results, "expected at least one module"
    for name, errs in results.items():
        assert errs == [], f"{name} has errors: {errs}"


def test_validator_catches_dangling_transition():
    bad = {
        "name": "bad",
        "states": {
            "Initial": {"type": "Initial", "direct_transition": "Nowhere"},
        },
    }
    errs = modules.validate_module(bad)
    assert any("unknown state" in e for e in errs)


def test_validator_catches_bad_distribution():
    bad = {
        "name": "bad",
        "states": {
            "Initial": {"type": "Initial", "direct_transition": "Roll"},
            "Roll": {"type": "Simple", "distributed_transition": [
                {"transition": "End", "distribution": 0.3},
                {"transition": "End", "distribution": 0.3},
            ]},
            "End": {"type": "Terminal"},
        },
    }
    errs = modules.validate_module(bad)
    assert any("sums to" in e for e in errs)


def test_validator_catches_unreachable():
    bad = {
        "name": "bad",
        "states": {
            "Initial": {"type": "Initial", "direct_transition": "End"},
            "End": {"type": "Terminal"},
            "Orphan": {"type": "Terminal"},
        },
    }
    errs = modules.validate_module(bad)
    assert any("unreachable" in e for e in errs)
