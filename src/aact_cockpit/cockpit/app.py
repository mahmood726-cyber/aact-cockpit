"""FastAPI cockpit. Single local user; serves a static JS frontend + a JSON API.

Run:  python -m uvicorn aact_cockpit.cockpit.app:app --host 127.0.0.1 --port 8000
   or: python scripts/serve.py

The Pydantic response models ARE the engine->frontend contract; field names
mirror aact_engine.contracts so there is one source of truth.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import json

from aact_engine.contracts import PICO
from aact_engine.nma import extract_contrasts
from aact_engine.query import cohort_search, effect_extraction, open_warehouse
from aact_cockpit.capsule.generate_capsule import emit, CapsuleInputError, CapsuleEmitError
from aact_cockpit.capsule.generate_tsa_capsule import emit as tsa_emit
from aact_cockpit.capsule.generate_nma_capsule import emit as nma_emit

_REPO = Path(__file__).resolve().parents[3]
_STATIC = Path(__file__).resolve().parent / "static"
_CAPSULES = _REPO / "capsules"
_ANALYSES = _REPO / "analyses"
_CAPSULES.mkdir(exist_ok=True)

app = FastAPI(title="AACT Cockpit", version="0.1.0")


# ----------------------------- request models ----------------------------- #
class CohortReq(BaseModel):
    population: str
    outcome: str
    intervention: str | None = None
    comparator: str | None = None
    limit: int = 4000


class EffectsReq(CohortReq):
    endpoint: str = "acm"
    estimand: str = "hazard ratio for all-cause mortality"


class BuildReq(BaseModel):
    effects: dict           # an EffectsDataset.to_dict() payload
    method: str = "PM"
    hksj: bool = False
    kind: str = "pairwise"  # "pairwise" | "tsa"


class NmaBuildReq(BaseModel):
    preset: str             # an analyses/<preset>.json config name (stem)


# ------------------------------- endpoints -------------------------------- #
@app.get("/api/health")
def health():
    try:
        con = open_warehouse()
    except SystemExit as e:
        raise HTTPException(503, str(e))
    try:
        meta = con.execute(
            "SELECT snapshot_date, table_name, row_count FROM _meta ORDER BY table_name"
        ).fetchall()
    finally:
        con.close()
    tables = {t: r for (d, t, r) in meta if t != "_all"}
    snap = next((d for (d, t, r) in meta if t == "_all"), None) or (meta[0][0] if meta else "?")
    return {"snapshot_date": snap, "tables": tables, "n_tables": len(tables)}


@app.post("/api/cohort")
def api_cohort(req: CohortReq):
    pico = PICO(population=req.population, outcome=req.outcome,
                intervention=req.intervention, comparator=req.comparator)
    con = open_warehouse()
    try:
        return cohort_search(pico, con=con, limit=req.limit)
    finally:
        con.close()


@app.post("/api/effects")
def api_effects(req: EffectsReq):
    pico = PICO(population=req.population, outcome=req.outcome,
                intervention=req.intervention, comparator=req.comparator)
    con = open_warehouse()
    try:
        cohort = cohort_search(pico, con=con, limit=req.limit)
        ncts = [t["nct_id"] for t in cohort["trials"]]
        ds = effect_extraction(ncts, pico=pico, primary_estimand=req.estimand,
                               endpoint=req.endpoint, con=con)
        out = ds.to_dict()
        out["cohort_n"] = cohort["n"]
        return out
    finally:
        con.close()


@app.post("/api/build")
def api_build(req: BuildReq):
    try:
        if req.kind == "tsa":
            man = tsa_emit(req.effects, _CAPSULES, method=req.method)
        else:
            man = emit(req.effects, _CAPSULES, method=req.method, hksj=req.hksj)
    except (CapsuleInputError, CapsuleEmitError) as e:
        raise HTTPException(422, str(e))
    slug = man["slug"]
    man["download_url"] = f"/capsules/{slug}/{slug}-capsule.html"
    return man


@app.get("/api/nma_presets")
def api_nma_presets():
    """Network-meta-analysis presets (analyses/*_nma.json configs)."""
    out = []
    for cfg_path in sorted(_ANALYSES.glob("*_nma.json")):
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        pico = cfg.get("pico", {})
        out.append({"id": cfg_path.stem,
                    "label": f"{pico.get('outcome', '?')} in {pico.get('population', '?')}"})
    return {"presets": out}


@app.post("/api/build_nma")
def api_build_nma(req: NmaBuildReq):
    cfg_path = _ANALYSES / f"{req.preset}.json"
    if not cfg_path.is_file():
        raise HTTPException(404, f"unknown NMA preset: {req.preset}")
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    con = open_warehouse()
    try:
        ex = extract_contrasts(cfg["condition"], cfg["outcome_like"], cfg["nodes"],
                               measure_like=cfg.get("measure_like", "hazard"), con=con)
    finally:
        con.close()
    if len(ex["contrasts"]) < 2:
        raise HTTPException(422, f"only {len(ex['contrasts'])} contrasts — not enough for a network")
    ds = {"pico": cfg["pico"], "primary_estimand": cfg["primary_estimand"],
          "measure": "HR", "reference": cfg.get("reference"),
          "lower_is_better": cfg.get("lower_is_better", True),
          "snapshot_date": ex["provenance"].get("snapshot_date"),
          "provenance": ex["provenance"], "contrasts": ex["contrasts"],
          "treatments": ex["treatments"], "notes": ex["notes"]}
    try:
        man = nma_emit(ds, _CAPSULES)
    except (CapsuleInputError, CapsuleEmitError) as e:
        raise HTTPException(422, str(e))
    slug = man["slug"]
    man["download_url"] = f"/capsules/{slug}/{slug}-capsule.html"
    man["n_contrasts"] = len(ex["contrasts"])
    return man


@app.get("/api/capsules")
def api_capsules():
    """List capsules already generated under capsules/, newest first."""
    out = []
    for sidecar in _CAPSULES.glob("*/*.json"):
        if sidecar.name == "assurance.json":
            continue
        try:
            c = json.loads(sidecar.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if "tier" not in c:
            continue
        if "pico" not in c and c.get("kind") not in ("atlas", "audit"):
            continue
        slug = c["slug"]
        html = _CAPSULES / slug / f"{slug}-capsule.html"
        if not html.is_file():
            continue
        n = (c.get("pooled", {}).get("k") or c.get("tsa", {}).get("k")
             or c.get("nma", {}).get("k") or c.get("scope", {}).get("n_analyses")
             or c.get("scope", {}).get("n_eligible") or "")
        out.append({"slug": slug, "title": c.get("title", slug),
                    "kind": c.get("kind", "pairwise"), "tier": c["tier"], "n": n,
                    "download_url": f"/capsules/{slug}/{slug}-capsule.html",
                    "mtime": html.stat().st_mtime})
    out.sort(key=lambda x: -x["mtime"])
    return {"capsules": out}


@app.get("/api/atlas")
def api_atlas():
    """Registry-wide meta-epidemiology atlas over the WHOLE warehouse — how often
    reported ratio analyses are significant, by sponsor class and trial size.
    Deterministic SQL (a few seconds); emits a self-auditing capsule."""
    from aact_engine.metaepi import registry_atlas
    from aact_cockpit.capsule.generate_atlas_capsule import emit as atlas_emit
    con = open_warehouse()
    try:
        data = registry_atlas(con=con)
    finally:
        con.close()
    try:
        man = atlas_emit(data, _CAPSULES)
    except (CapsuleInputError, CapsuleEmitError) as e:
        raise HTTPException(422, str(e))
    slug = man["slug"]
    man["download_url"] = f"/capsules/{slug}/{slug}-capsule.html"
    return man


@app.get("/api/audits")
def api_audits():
    """List the available ct.gov registry-audit reproductions."""
    from aact_engine.audits import AUDITS
    titles = {
        "ctgov-stopped-trial-disclosure-gap": "Stopped-trial disclosure gap",
        "ctgov-condition-hiddenness-map": "Condition hiddenness map",
        "ctgov-rule-era-reporting-gap": "Rule-era reporting gap",
        "ctgov-probable-act-fdaaa-debt": "Probable ACT / FDAAA reporting debt",
    }
    return {"audits": [{"id": a, "label": titles.get(a, a)} for a in AUDITS]}


@app.get("/api/audit")
def api_audit(audit: str):
    """Run one ct.gov registry audit over the warehouse and emit its capsule."""
    from aact_engine.audits import run_audit, AUDITS
    from aact_cockpit.capsule.generate_audit_capsule import emit as audit_emit
    if audit not in AUDITS:
        raise HTTPException(404, f"unknown audit {audit!r}")
    con = open_warehouse()
    try:
        data = run_audit(audit, con=con)
    finally:
        con.close()
    try:
        man = audit_emit(data, _CAPSULES)
    except (CapsuleInputError, CapsuleEmitError) as e:
        raise HTTPException(422, str(e))
    slug = man["slug"]
    man["download_url"] = f"/capsules/{slug}/{slug}-capsule.html"
    return man


@app.get("/", response_class=HTMLResponse)
def index():
    idx = _STATIC / "index.html"
    if not idx.is_file():
        return HTMLResponse("<h1>AACT Cockpit</h1><p>frontend not built</p>")
    return HTMLResponse(idx.read_text(encoding="utf-8"))


# serve generated capsules for download/preview
app.mount("/capsules", StaticFiles(directory=str(_CAPSULES)), name="capsules")
