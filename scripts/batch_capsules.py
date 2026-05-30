"""Batch capsule production: a JSON list of PICOs -> many self-auditing capsules
+ an offline index.html. One warehouse, one engine, config-only — this is the
"produce large-scale analysis easily" path.

Usage:
    python scripts/batch_capsules.py --config analyses/cardiometabolic.json --out capsules
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aact_engine.contracts import PICO
from aact_engine.query import cohort_search, effect_extraction, open_warehouse
from aact_cockpit.capsule.generate_capsule import emit, CapsuleInputError, CapsuleEmitError

MIN_K = 2  # need >=2 trials to pool


def run(config_path: Path, out_dir: Path) -> list[dict]:
    spec = json.loads(config_path.read_text(encoding="utf-8"))
    con = open_warehouse()
    results = []
    try:
        for a in spec["analyses"]:
            pico = PICO(population=a["population"], outcome=a["outcome"],
                        intervention=a.get("intervention"), comparator=a.get("comparator"))
            t0 = time.time()
            try:
                cohort = cohort_search(pico, con=con, limit=a.get("limit", 6000))
                ncts = [t["nct_id"] for t in cohort["trials"]]
                ds = effect_extraction(ncts, pico=pico, primary_estimand=a["estimand"],
                                       endpoint=a["endpoint"], con=con)
                row = {"population": a["population"], "outcome": a["outcome"],
                       "endpoint": a["endpoint"], "cohort_n": cohort["n"],
                       "k": ds.n_studies, "elapsed": round(time.time() - t0, 1)}
                if ds.n_studies < MIN_K:
                    row["status"] = f"skipped (k={ds.n_studies} < {MIN_K})"
                    results.append(row)
                    print(f"  - {a['population']:22s} / {a['endpoint']:9s}  {row['status']}")
                    continue
                man = emit(ds.to_dict(), out_dir)
                row.update({"status": "ok", "slug": man["slug"], "tier": man["tier"],
                            "html": f"{man['slug']}/{man['slug']}-capsule.html"})
                results.append(row)
                print(f"  + {a['population']:22s} / {a['endpoint']:9s}  k={ds.n_studies:<3d} tier={man['tier']}")
            except (CapsuleInputError, CapsuleEmitError) as e:
                results.append({"population": a["population"], "endpoint": a["endpoint"],
                                "status": f"error: {e}", "k": 0})
                print(f"  ! {a['population']:22s} / {a['endpoint']:9s}  error: {e}")
    finally:
        con.close()
    return results


INDEX_CSS = (
    "body{font:15px/1.5 -apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:900px;"
    "margin:40px auto;padding:0 18px;color:#1a1a1f}h1{font-size:22px}"
    "table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:7px 9px;"
    "border-bottom:1px solid #e3e3ea;text-align:left}.t{font-weight:800;padding:2px 8px;"
    "border-radius:5px;color:#fff;font-size:12px;text-transform:uppercase}"
    ".silver{background:#8a8f99}.bronze{background:#a9712e}.gold{background:#b8860b}.none{background:#b33}"
    "a{color:#2456c6;text-decoration:none}.muted{color:#5a5a66;font-size:13px}"
)


def write_index(results: list[dict], out_dir: Path, snapshot: str) -> Path:
    ok = [r for r in results if r.get("status") == "ok"]
    rows = ""
    for r in results:
        if r.get("status") == "ok":
            tier = r["tier"]
            link = f'<a href="{r["html"]}">{r["population"]} — {r["outcome"]}</a>'
            badge = f'<span class="t {tier}">{tier}</span>'
            rows += f"<tr><td>{link}</td><td>{r['endpoint']}</td><td>{r['k']}</td><td>{badge}</td></tr>"
        else:
            rows += (f"<tr><td>{r['population']} — {r.get('outcome','')}</td><td>{r['endpoint']}</td>"
                     f"<td>{r.get('k',0)}</td><td class='muted'>{r['status']}</td></tr>")
    html = (
        f"<!doctype html><html><head><meta charset='utf-8'><title>AACTCockpit capsules</title>"
        f"<style>{INDEX_CSS}</style></head><body>"
        f"<h1>AACTCockpit — capsule portfolio</h1>"
        f"<p class='muted'>{len(ok)} self-auditing pairwise meta-analyses produced from one AACT "
        f"warehouse (snapshot {snapshot}), one engine, config only.</p>"
        f"<table><tr><th>Analysis</th><th>Endpoint</th><th>k</th><th>Assurance</th></tr>{rows}</table>"
        f"</body></html>"
    )
    idx = out_dir / "index.html"
    idx.write_text(html, encoding="utf-8")
    return idx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", default="capsules")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    results = run(Path(args.config), out)
    # read snapshot from any ok capsule's sidecar, else from warehouse
    snapshot = "?"
    for r in results:
        if r.get("status") == "ok":
            side = out / r["slug"] / f"{r['slug']}.json"
            snapshot = json.loads(side.read_text(encoding="utf-8")).get("snapshot_date", "?")
            break
    idx = write_index(results, out, snapshot)
    ok = sum(1 for r in results if r.get("status") == "ok")
    print(f"\n{ok}/{len(results)} capsules produced in {time.time()-t0:.1f}s -> {idx}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
