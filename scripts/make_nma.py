"""CLI: NMA config JSON -> network meta-analysis capsule.

Extracts oriented contrasts from AACT, fits the NMA, and (optionally) marks the
analysis_rerun witness as passed if R netmeta cross-validation succeeded.

Usage:
    python scripts/make_nma.py --config analyses/af_anticoag_nma.json --out capsules [--r-validated]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aact_engine.nma import extract_contrasts  # noqa: E402
from aact_cockpit.capsule.generate_nma_capsule import emit  # noqa: E402
from aact_cockpit.capsule.nma import nma  # noqa: E402


def build_dataset(cfg: dict, con=None) -> dict:
    ex = extract_contrasts(cfg["condition"], cfg["outcome_like"], cfg["nodes"],
                           measure_like=cfg.get("measure_like", "hazard"), con=con)
    return {
        "pico": cfg["pico"], "primary_estimand": cfg["primary_estimand"],
        "measure": "HR", "reference": cfg.get("reference"),
        "snapshot_date": ex["provenance"].get("snapshot_date"),
        "provenance": ex["provenance"], "contrasts": ex["contrasts"],
        "treatments": ex["treatments"], "notes": ex["notes"],
        "transitivity": ex.get("transitivity", {}),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default="capsules")
    ap.add_argument("--r-validated", action="store_true",
                    help="mark analysis_rerun=pass (run r_validate_nma.R separately to earn this)")
    ap.add_argument("--dump-contrasts", default=None, help="also write the contrasts JSON here (for R)")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    ds = build_dataset(cfg)
    if len(ds["contrasts"]) < 2:
        print(f"only {len(ds['contrasts'])} contrasts — not enough for an NMA")
        return 1
    if args.r_validated:
        ds["analysis_rerun"] = "pass"
    if args.dump_contrasts:
        Path(args.dump_contrasts).parent.mkdir(parents=True, exist_ok=True)
        Path(args.dump_contrasts).write_text(json.dumps(ds["contrasts"], indent=1), encoding="utf-8")
        # also dump the python NMA result for the R comparison
        res = nma(ds["contrasts"], reference=ds["reference"])
        py = {k: res[k] for k in ("treatments", "reference", "tau2", "rel_to_ref", "sucra")}
        Path(args.dump_contrasts).with_name("af_nma_py.json").write_text(
            json.dumps(py, indent=1, default=float), encoding="utf-8")

    man = emit(ds, args.out)
    print(json.dumps(man, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
