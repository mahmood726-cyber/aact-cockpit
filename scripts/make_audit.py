"""CLI: compute a ct.gov registry audit and emit its self-auditing capsule.

Usage:
    python scripts/make_audit.py --audit ctgov-stopped-trial-disclosure-gap --out docs
    python scripts/make_audit.py --all --out docs
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aact_engine.audits import run_audit, AUDITS  # noqa: E402
from aact_engine.query import open_warehouse  # noqa: E402
from aact_cockpit.capsule.generate_audit_capsule import emit  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", default=None, choices=list(AUDITS))
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default="capsules")
    ap.add_argument("--db", default=None)
    args = ap.parse_args()
    ids = list(AUDITS) if args.all else [args.audit]
    if not ids or ids == [None]:
        ap.error("pass --audit <id> or --all")
    con = open_warehouse(args.db)
    try:
        for aid in ids:
            data = run_audit(aid, con=con)
            man = emit(data, args.out)
            print(json.dumps(man, indent=2))
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
