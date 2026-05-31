"""CLI: compute the registry meta-epidemiology atlas and emit its capsule.

Usage:
    python scripts/make_atlas.py --out capsules          # compute from warehouse
    python scripts/make_atlas.py --in effects/atlas.json --out capsules  # from cached dump
    python scripts/make_atlas.py --dump effects/atlas.json               # just compute + dump
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aact_cockpit.capsule.generate_atlas_capsule import emit  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=None, help="cached atlas JSON (skip warehouse)")
    ap.add_argument("--out", default="capsules")
    ap.add_argument("--dump", default=None, help="write computed atlas JSON here and exit")
    ap.add_argument("--db", default=None, help="warehouse path override")
    args = ap.parse_args()

    if args.inp:
        atlas = json.loads(Path(args.inp).read_text(encoding="utf-8"))
    else:
        from aact_engine.metaepi import registry_atlas
        atlas = registry_atlas(db_path=args.db)

    if args.dump:
        Path(args.dump).parent.mkdir(parents=True, exist_ok=True)
        Path(args.dump).write_text(json.dumps(atlas, indent=2), encoding="utf-8")
        print(f"dumped atlas -> {args.dump}")
        return 0

    print(json.dumps(emit(atlas, args.out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
