"""Command-line entrypoint: `synthea-nemotron <command>`.

Pipeline order:
  status -> personas -> geography -> calibrate -> validate -> narratives
         -> bootstrap -> stage -> generate

`all` runs the host-independent steps (everything up to and including narratives
+ calibration + module validation), which is the Phase-1 demo artifact that needs
no JDK. `generate` additionally requires a Synthea checkout and a JDK.
"""
from __future__ import annotations

import argparse
import json

from . import (bootstrap, calibration, config, generate, geography, modules,
               narratives, personas)


def _print(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))


def cmd_status(args):
    config.ensure_dirs()
    cached = sorted(config.PERSONAS_DIR.glob("*.parquet"))
    _print({
        "dataset": config.HF_DATASET,
        "personas_cached_shards": [p.name for p in cached],
        "personas_source": "local cache" if cached else "remote (HuggingFace)",
        "modules": [p.name for p in config.MODULES_DIR.glob("*.json")],
        **bootstrap.status(),
    })


def cmd_personas(args):
    rows = personas.department_summary(max_shards=args.max_shards)
    print("department            n      pct_urban  mean_age")
    for dep, n, pu, ma in rows:
        print(f"{dep:<20} {n:>6}   {pu:>6}   {ma:>6}")


def cmd_geography(args):
    config.ensure_dirs()
    _print(geography.build(max_shards=args.max_shards))


def cmd_calibrate(args):
    _print(calibration.write_report())


def cmd_validate(args):
    results = modules.validate_all()
    ok = True
    for name, errs in results.items():
        if errs:
            ok = False
            print(f"✗ {name}")
            for e in errs:
                print(f"    - {e}")
        else:
            print(f"✓ {name}")
    if not ok:
        raise SystemExit(1)


def cmd_narratives(args):
    _print(narratives.generate_sample(n=args.n, seed=args.seed,
                                      max_shards=args.max_shards))


def cmd_bootstrap(args):
    java = bootstrap.check_java()
    if not java:
        print(bootstrap.JAVA_HINT)
    print("downloading Synthea fat-jar (~190 MB)…")
    path = bootstrap.download_jar()
    _print({"synthea_jar": str(path), "java": java})


def cmd_stage(args):
    _print(generate.stage())


def cmd_generate(args):
    if not (config.BUILD_DIR / "synthea" / "geography" / "sv_demographics.csv").exists():
        geography.build(max_shards=args.max_shards)
    staged = generate.stage()
    result = generate.run(population=args.population, seed=args.seed,
                          dry_run=args.dry_run)
    narr = None
    if result.get("status") == "ok":
        from pathlib import Path
        csv_dir = Path(result["output_dir"]) / "csv"
        if (csv_dir / "patients.csv").exists():
            narr = narratives.from_synthea_output(csv_dir)
    _print({"staged": staged, "run": result, "clinical_narratives": narr})


def cmd_all(args):
    """Host-independent Phase-1 artifact (no JDK required)."""
    config.ensure_dirs()
    print("== geography =="); geo = geography.build(max_shards=args.max_shards); _print(geo)
    print("== calibrate ==");  _print(calibration.write_report())
    print("== validate modules ==")
    results = modules.validate_all()
    for name, errs in results.items():
        print(f"  {'✓' if not errs else '✗'} {name}")
        for e in errs:
            print(f"      - {e}")
    print("== narratives ==")
    _print(narratives.generate_sample(n=args.n, seed=args.seed, max_shards=args.max_shards))
    if any(errs for errs in results.values()):
        raise SystemExit(1)


def main(argv=None):
    p = argparse.ArgumentParser(prog="synthea-nemotron",
                                description="Sovereign Synthetic Dataset — Phase 1")
    p.add_argument("--max-shards", type=int, default=None,
                   help="limit Nemotron parquet shards read (1-3; default all)")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="show environment + dataset status").set_defaults(func=cmd_status)
    sub.add_parser("personas", help="department summary of the persona spine").set_defaults(func=cmd_personas)
    sub.add_parser("geography", help="build Synthea SV geography CSVs").set_defaults(func=cmd_geography)
    sub.add_parser("calibrate", help="write calibration directives report").set_defaults(func=cmd_calibrate)
    sub.add_parser("validate", help="validate custom Synthea modules").set_defaults(func=cmd_validate)

    pn = sub.add_parser("narratives", help="generate Spanish narratives (social/demographic)")
    pn.add_argument("-n", type=int, default=25); pn.add_argument("--seed", type=int, default=1)
    pn.set_defaults(func=cmd_narratives)

    sub.add_parser("bootstrap", help="download the Synthea fat-jar (needs JDK 17+ to run)").set_defaults(func=cmd_bootstrap)
    sub.add_parser("stage", help="assemble the SV run directory").set_defaults(func=cmd_stage)

    pg = sub.add_parser("generate", help="run a Synthea SV generation (needs JDK)")
    pg.add_argument("-p", "--population", type=int, default=1000)
    pg.add_argument("--seed", type=int, default=1)
    pg.add_argument("--dry-run", action="store_true")
    pg.set_defaults(func=cmd_generate)

    pa = sub.add_parser("all", help="run host-independent Phase-1 artifact (no JDK)")
    pa.add_argument("-n", type=int, default=25); pa.add_argument("--seed", type=int, default=1)
    pa.set_defaults(func=cmd_all)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
