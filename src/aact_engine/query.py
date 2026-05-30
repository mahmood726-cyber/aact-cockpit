"""Public query API over the AACT DuckDB warehouse.

Three functions, each carrying snapshot provenance:
    cohort_search(pico)        -> matching randomized interventional trials
    get_outcome_analyses(ids)  -> joined analysis rows + arm titles (p-value-only dropped)
    effect_extraction(ids,...) -> EffectsDataset (log-scale yi/sei, guarded)
"""
from __future__ import annotations

import re
from pathlib import Path

import duckdb

from .contracts import PICO, ArmEffect, EffectRecord, EffectsDataset
from .effects import extract_effect
from .guards import assert_columns_exist
from .ingest import default_db_path, read_provenance
from .paths import discover_snapshot_root, detect_snapshot_date
from .provenance import Provenance
from .taxonomy import classify_endpoint

_PLACEBO_RE = re.compile(r"\b(placebo|sham|usual care|standard of care|control)\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"(\d{4})")


# --------------------------------------------------------------------------- #
# connection helpers
# --------------------------------------------------------------------------- #
def open_warehouse(db_path: str | Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open the default (or given) warehouse read-only."""
    if db_path is None:
        snap = discover_snapshot_root()
        db_path = default_db_path(detect_snapshot_date(snap))
    if not Path(db_path).is_file():
        raise SystemExit(
            f"Warehouse not built: {db_path}. Run scripts/build_warehouse.py first."
        )
    return duckdb.connect(str(db_path), read_only=True)


def _provenance(con, db_path=None) -> Provenance:
    try:
        row = con.execute(
            "SELECT snapshot_date FROM _meta WHERE table_name='_all' LIMIT 1"
        ).fetchone()
        if not row:
            row = con.execute("SELECT snapshot_date FROM _meta LIMIT 1").fetchone()
        date = row[0] if row else "unknown"
    except duckdb.Error:
        date = "unknown"
    return Provenance(snapshot_date=date, db_path=str(db_path) if db_path else None).with_extracted_now()


# --------------------------------------------------------------------------- #
# cohort search
# --------------------------------------------------------------------------- #
def cohort_search(pico: PICO, con=None, db_path=None, limit: int = 1000) -> dict:
    """Return randomized interventional trials with posted results matching the
    PICO condition (and optional intervention drug-class), newest first."""
    owns = con is None
    if owns:
        con = open_warehouse(db_path)
    try:
        assert_columns_exist(con, "studies", ("nct_id", "study_type", "results_first_posted_date"))
        assert_columns_exist(con, "designs", ("nct_id", "allocation"))
        assert_columns_exist(con, "conditions", ("nct_id", "downcase_name"))

        cond = f"%{pico.population.lower()}%"
        sql = """
            SELECT DISTINCT s.nct_id,
                   COALESCE(s.official_title, s.brief_title) AS title,
                   s.start_date, s.enrollment
            FROM studies s
            JOIN designs d ON d.nct_id = s.nct_id
            JOIN conditions c ON c.nct_id = s.nct_id
            WHERE lower(s.study_type) = 'interventional'
              AND lower(d.allocation) = 'randomized'
              AND s.results_first_posted_date IS NOT NULL
              AND c.downcase_name LIKE ?
            ORDER BY s.start_date DESC NULLS LAST
            LIMIT ?
        """
        rows = con.execute(sql, [cond, limit]).fetchall()
        trials = []
        for nct, title, start_date, enrollment in rows:
            yr = _year_of(start_date)
            trials.append({
                "nct_id": nct, "title": title, "year": yr,
                "enrollment": _int_or_none(enrollment),
            })
        prov = _provenance(con, db_path)
        return {"trials": trials, "n": len(trials),
                "pico": pico.to_dict(), "provenance": prov.to_dict()}
    finally:
        if owns:
            con.close()


# --------------------------------------------------------------------------- #
# outcome analyses (joined with arm titles)
# --------------------------------------------------------------------------- #
def get_outcome_analyses(nct_ids, con=None, db_path=None) -> list[dict]:
    """Joined outcome_analyses rows with the two arm titles. p-value-only rows
    (no estimate + CI) are dropped. Returns row dicts ready for extract_effect."""
    if not nct_ids:
        return []
    owns = con is None
    if owns:
        con = open_warehouse(db_path)
    try:
        for t, cols in (
            ("outcome_analyses", ("id", "nct_id", "outcome_id", "param_type",
                                  "param_value", "ci_lower_limit", "ci_upper_limit",
                                  "ci_percent", "method")),
            ("outcomes", ("id", "title")),
            ("outcome_analysis_groups", ("outcome_analysis_id", "result_group_id")),
            ("result_groups", ("id", "title")),
            ("studies", ("nct_id", "start_date", "brief_title", "official_title")),
        ):
            assert_columns_exist(con, t, cols)

        placeholders = ",".join("?" for _ in nct_ids)
        sql = f"""
            SELECT oa.id            AS outcome_analysis_id,
                   oa.nct_id        AS nct_id,
                   oa.outcome_id    AS outcome_id,
                   oa.param_type    AS param_type,
                   oa.param_value   AS param_value,
                   oa.ci_lower_limit AS ci_lower_limit,
                   oa.ci_upper_limit AS ci_upper_limit,
                   oa.ci_percent    AS ci_percent,
                   oa.method        AS method,
                   oc.title         AS outcome_title,
                   COALESCE(s.official_title, s.brief_title) AS study_title,
                   s.start_date     AS start_date,
                   string_agg(rg.title, '||' ORDER BY rg.id) AS arm_titles,
                   count(rg.id)     AS n_arms
            FROM outcome_analyses oa
            JOIN outcomes oc ON oc.id = oa.outcome_id
            LEFT JOIN studies s ON s.nct_id = oa.nct_id
            LEFT JOIN outcome_analysis_groups oag ON oag.outcome_analysis_id = oa.id
            LEFT JOIN result_groups rg ON rg.id = oag.result_group_id
            WHERE oa.nct_id IN ({placeholders})
              AND oa.param_value IS NOT NULL
              AND oa.ci_lower_limit IS NOT NULL
              AND oa.ci_upper_limit IS NOT NULL
            GROUP BY 1,2,3,4,5,6,7,8,9,10,11,12
        """
        out = []
        for r in con.execute(sql, list(nct_ids)).fetchall():
            d = {
                "outcome_analysis_id": r[0], "nct_id": r[1], "outcome_id": r[2],
                "param_type": r[3], "param_value": r[4], "ci_lower_limit": r[5],
                "ci_upper_limit": r[6], "ci_percent": r[7], "method": r[8],
                "outcome_title": r[9], "study_label": r[10], "start_date": r[11],
                "arm_titles": r[12], "n_arms": r[13],
            }
            out.append(d)
        return out
    finally:
        if owns:
            con.close()


# --------------------------------------------------------------------------- #
# effect extraction -> EffectsDataset
# --------------------------------------------------------------------------- #
def effect_extraction(nct_ids, pico: PICO, primary_estimand: str,
                      endpoint: str = "acm", con=None, db_path=None) -> EffectsDataset:
    owns = con is None
    if owns:
        con = open_warehouse(db_path)
    try:
        prov = _provenance(con, db_path)
        rows = get_outcome_analyses(nct_ids, con=con)
        records: list[EffectRecord] = []
        notes: list[str] = []
        seen = set()
        for d in rows:
            if classify_endpoint(d.get("outcome_title")) != endpoint:
                continue
            d["endpoint"] = endpoint
            d["year"] = _year_of(d.get("start_date"))
            d["arm_experimental"], d["arm_comparator"] = _split_arms(d.get("arm_titles"))
            rec = extract_effect(d)
            if rec is None:
                notes.append(f"skipped {d['nct_id']} analysis {d['outcome_analysis_id']} "
                             f"(param_type={d.get('param_type')!r}, no usable estimate)")
                continue
            # one record per trial: keep the first usable mortality analysis
            if rec.nct_id in seen:
                continue
            seen.add(rec.nct_id)
            records.append(rec)

        measure = _dominant_measure(records)
        return EffectsDataset(
            records=records, provenance=prov, pico=pico,
            primary_estimand=primary_estimand, measure=measure,
            n_studies=len(records), notes=notes,
        )
    finally:
        if owns:
            con.close()


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #
def _split_arms(arm_titles: str | None):
    if not arm_titles:
        return None, None
    parts = [p.strip() for p in arm_titles.split("||") if p.strip()]
    if len(parts) < 2:
        return None, None
    comparator = next((p for p in parts if _PLACEBO_RE.search(p)), None)
    if comparator is not None:
        experimental = next((p for p in parts if p != comparator), parts[0])
    else:
        experimental, comparator = parts[0], parts[1]
    return ArmEffect(label=experimental), ArmEffect(label=comparator)


def _dominant_measure(records) -> str:
    if not records:
        return ""
    counts: dict[str, int] = {}
    for r in records:
        counts[r.measure_type] = counts.get(r.measure_type, 0) + 1
    return max(counts, key=counts.get)


def _year_of(start_date) -> int | None:
    if not start_date:
        return None
    m = _YEAR_RE.search(str(start_date))
    return int(m.group(1)) if m else None


def _int_or_none(x):
    try:
        return int(float(str(x)))
    except (ValueError, TypeError):
        return None


__all__ = ["open_warehouse", "cohort_search", "get_outcome_analyses", "effect_extraction"]
