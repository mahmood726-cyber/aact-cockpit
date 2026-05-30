"""CLI: PICO -> effects dataset JSON (the engine->capsule contract artifact).

This is the headless/batch path (the FastAPI cockpit calls the same engine
functions for the interactive path). Large-scale use: drive it from a YAML/CSV
of PICOs to emit many effects datasets, then feed each to the capsule generator.

Usage:
    python scripts/extract_effects.py --population "heart failure" \
        --outcome "all-cause mortality" --endpoint acm \
        --estimand "hazard ratio for all-cause mortality" \
        --out effects/cardio_mortality.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aact_engine.contracts import PICO  # noqa: E402
from aact_engine.query import cohort_search, effect_extraction, open_warehouse  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--population", required=True)
    ap.add_argument("--outcome", required=True)
    ap.add_argument("--intervention", default=None)
    ap.add_argument("--comparator", default=None)
    ap.add_argument("--endpoint", default="acm", help="classify_endpoint id (acm, cv_death, ...)")
    ap.add_argument("--estimand", required=True, help="named primary estimand")
    ap.add_argument("--limit", type=int, default=5000)
    ap.add_argument("--out", required=True)
    ap.add_argument("--db", default=None)
    args = ap.parse_args()

    pico = PICO(population=args.population, outcome=args.outcome,
                intervention=args.intervention, comparator=args.comparator)
    con = open_warehouse(args.db)
    try:
        cohort = cohort_search(pico, con=con, limit=args.limit)
        ncts = [t["nct_id"] for t in cohort["trials"]]
        ds = effect_extraction(ncts, pico=pico, primary_estimand=args.estimand,
                               endpoint=args.endpoint, con=con)
    finally:
        con.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(ds.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"cohort searched: {cohort['n']} trials")
    print(f"effects extracted: {ds.n_studies} trials (measure={ds.measure})")
    print(f"skipped: {len(ds.notes)} analyses")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
