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

from aact_engine.contracts import PICO
from aact_engine.query import cohort_search, effect_extraction, open_warehouse
from aact_cockpit.capsule.generate_capsule import emit, CapsuleInputError, CapsuleEmitError

_REPO = Path(__file__).resolve().parents[3]
_STATIC = Path(__file__).resolve().parent / "static"
_CAPSULES = _REPO / "capsules"
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
        man = emit(req.effects, _CAPSULES, method=req.method, hksj=req.hksj)
    except (CapsuleInputError, CapsuleEmitError) as e:
        raise HTTPException(422, str(e))
    slug = man["slug"]
    pooled = req.effects  # frontend already has effects; pooled is recomputed client-side too
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
