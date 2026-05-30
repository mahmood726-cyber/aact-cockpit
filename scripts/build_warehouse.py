"""CLI: build the AACT DuckDB warehouse from the discovered snapshot.

Usage:
    python scripts/build_warehouse.py            # MVP tables, idempotent
    python scripts/build_warehouse.py --rebuild  # force rebuild
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aact_engine.ingest import build_warehouse  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aact-root", default=None, help="Snapshot root (holds studies.txt)")
    ap.add_argument("--db", default=None, help="Output DuckDB path")
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    t0 = time.time()
    prov = build_warehouse(
        snapshot_root=args.aact_root, db_path=args.db, rebuild=args.rebuild
    )
    print(f"\nWarehouse ready: {prov.db_path}")
    print(f"Snapshot date:  {prov.snapshot_date}")
    print(f"Elapsed:        {time.time()-t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
