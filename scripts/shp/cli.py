"""``shp`` — one entrypoint over the whole pipeline.

    shp synthea <cmd>   the SV Synthea pipeline (personas, geography, generate, ...)
                             run `shp synthea -h` for its subcommands
    shp etl [csv_dir]   Synthea CSV -> OMOP CDM v5.4 (DuckDB) + quality gate
    shp quality <db>    run the data-quality gate on an OMOP DuckDB
    shp study diabetes  semi-synthetic causal answer-key (no Java needed)
    shp build-samples   regenerate the checked-in OMOP/ + FHIR/ Colab samples
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config

# Sentinel: `--vocab` given with no path → use the bundled starter crosswalk.
_STARTER = "\x00starter"


def _cmd_etl(args) -> int:
    from .omop import etl_synthea, vocabulary
    from .quality.checks import run_quality_gate

    csv_dir = args.csv_dir or config.synthea_csv_dir()
    if not csv_dir:
        print("No Synthea CSV found under data/build. Run `shp synthea generate` "
              "first, or pass a CSV directory explicitly.", file=sys.stderr)
        return 1
    concept_map = None
    if args.vocab is not None:
        path = config.STARTER_CROSSWALK if args.vocab == _STARTER else args.vocab
        concept_map = vocabulary.load_crosswalk(path)
        print(f"vocabulary crosswalk: {len(concept_map)} codes mapped to standard "
              f"concepts (from {Path(path).name})")
    db = etl_synthea.etl(csv_dir, db_path=config.SV_OMOP_DB,
                         source_name=config.CDM_SOURCE_SV, concept_map=concept_map)
    print(f"ETL complete → {db}")
    print(run_quality_gate(db))
    return 0


def _cmd_quality(args) -> int:
    from .quality.checks import run_quality_gate
    print(run_quality_gate(args.db))
    return 0


def _cmd_study_diabetes(args) -> int:
    from .study.diabetes import run as study
    config.ensure_dirs()
    report = study.run(n=args.n, seed=args.seed, do_omop=not args.no_omop)
    print(study.format_report(report))
    return 0


def _cmd_build_samples(args) -> int:
    from . import samples
    return samples.build(omop=not args.fhir_only, fhir=not args.omop_only,
                         fhir_src=args.fhir_src)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="shp", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    # `synthea` is intercepted in main() and forwarded to the synthea sub-CLI;
    # declared here only so it shows up in `shp -h`.
    sy = sub.add_parser("synthea", add_help=False,
                        help="SV Synthea pipeline — run `shp synthea -h`")
    sy.add_argument("rest", nargs=argparse.REMAINDER)

    e = sub.add_parser("etl", help="ETL a Synthea CSV dir into OMOP + quality gate")
    e.add_argument("csv_dir", nargs="?", default=None,
                   help="Synthea CSV dir (default: auto-detect under data/build)")
    e.add_argument("--vocab", nargs="?", const=_STARTER, default=None, metavar="CROSSWALK.csv",
                   help="apply a source-code→standard concept_id crosswalk (the vocabulary "
                        "seam); omit the path to use the bundled starter crosswalk")
    e.set_defaults(func=_cmd_etl)

    q = sub.add_parser("quality", help="run the quality gate on an OMOP DuckDB")
    q.add_argument("db", help="path to an OMOP .duckdb")
    q.set_defaults(func=_cmd_quality)

    st = sub.add_parser("study", help="run a study")
    stsub = st.add_subparsers(dest="study", required=True)
    d = stsub.add_parser("diabetes", help="semi-synthetic answer-key (naive→IPTW→AIPW→TMLE)")
    d.add_argument("-n", type=int, default=6000)
    d.add_argument("--seed", type=int, default=42)
    d.add_argument("--no-omop", action="store_true",
                   help="skip the OMOP round-trip (estimate on the in-memory frame)")
    d.set_defaults(func=_cmd_study_diabetes)

    b = sub.add_parser("build-samples", help="regenerate the checked-in Colab samples")
    b.add_argument("--omop-only", action="store_true", help="only the OMOP 100-person subset")
    b.add_argument("--fhir-only", action="store_true", help="only the curated FHIR bundle")
    b.add_argument("--fhir-src", default=None,
                   help="source FHIR bundle/dir to curate (default: data/build FHIR output)")
    b.set_defaults(func=_cmd_build_samples)

    return p


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Forward the whole SV pipeline to its own argparse tree.
    if argv and argv[0] == "synthea":
        from .synthea import cli as synthea_cli
        synthea_cli.main(argv[1:])
        return 0

    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
