"""CLI: effects dataset JSON -> Trial Sequential Analysis capsule.

Usage:
    python scripts/make_tsa.py --in effects/cardio_mortality.json --out capsules
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aact_cockpit.capsule.generate_tsa_capsule import emit  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", default="capsules")
    ap.add_argument("--method", default="PM", choices=["PM", "DL"])
    args = ap.parse_args()
    ds = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    print(json.dumps(emit(ds, args.out, method=args.method), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
