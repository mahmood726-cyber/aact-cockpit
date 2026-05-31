"""Network meta-analysis contrast extraction from AACT.

Builds oriented log-effect contrasts (treat1 vs treat2, experimental vs
comparator) for a condition + outcome, mapping each arm to a treatment node via
a caller-supplied keyword map. One contrast per (trial, edge), deterministic
(lowest outcome_analysis id). Carries snapshot provenance.
"""
from __future__ import annotations

import math
import re

from .effects import Z95
from .guards import assert_columns_exist
from .query import open_warehouse, _provenance


def classify_node(title: str, nodes: dict[str, list[str]]) -> str | None:
    """Map an arm title to a treatment node by WORD-BOUNDARY keyword match (so a
    drug name embedded in another token cannot mis-route the contrast)."""
    tl = (title or "").lower()
    for name, kws in nodes.items():
        for k in kws:
            if re.search(r"\b" + re.escape(k.lower()) + r"\b", tl):
                return name
    return None


def extract_contrasts(condition: str, outcome_like, nodes: dict[str, list[str]],
                      measure_like: str = "hazard", con=None, db_path=None) -> dict:
    """condition: substring on conditions.downcase_name. outcome_like: str or
    list of substrings matched against outcomes.title. nodes: {node_name:[kw]}."""
    owns = con is None
    if owns:
        con = open_warehouse(db_path)
    if isinstance(outcome_like, str):
        outcome_like = [outcome_like]
    try:
        for t, cols in (("outcome_analyses", ("id", "nct_id", "outcome_id", "param_type",
                                              "param_value", "ci_lower_limit", "ci_upper_limit")),
                        ("outcomes", ("id", "title")),
                        ("result_groups", ("id", "title", "ctgov_group_code"))):
            assert_columns_exist(con, t, cols)
        prov = _provenance(con, db_path)
        out_clause = " OR ".join(["lower(oc.title) LIKE ?"] * len(outcome_like))
        sql = f"""
            SELECT oa.id, oa.nct_id, oa.param_value, oa.ci_lower_limit, oa.ci_upper_limit,
                   COALESCE(s.official_title, s.brief_title) AS study_title,
                   string_agg(rg.title, '||' ORDER BY rg.ctgov_group_code) AS arms,
                   count(rg.id) AS n_arms
            FROM outcome_analyses oa
            JOIN outcomes oc ON oc.id = oa.outcome_id
            JOIN studies s ON s.nct_id = oa.nct_id
            JOIN designs d ON d.nct_id = oa.nct_id
            JOIN conditions c ON c.nct_id = oa.nct_id
            LEFT JOIN outcome_analysis_groups oag ON oag.outcome_analysis_id = oa.id
            LEFT JOIN result_groups rg ON rg.id = oag.result_group_id
            WHERE c.downcase_name LIKE ?
              AND lower(s.study_type) = 'interventional'
              AND lower(d.allocation) = 'randomized'
              AND s.results_first_posted_date IS NOT NULL
              AND ({out_clause})
              AND lower(oa.param_type) LIKE ?
              AND oa.param_value IS NOT NULL
              AND oa.ci_lower_limit IS NOT NULL AND oa.ci_upper_limit IS NOT NULL
            GROUP BY oa.id, oa.nct_id, oa.param_value, oa.ci_lower_limit, oa.ci_upper_limit, study_title
            HAVING count(rg.id) = 2
            ORDER BY oa.nct_id, CAST(oa.id AS BIGINT)
        """
        params = [f"%{condition.lower()}%"] + [f"%{o.lower()}%" for o in outcome_like] + [f"%{measure_like.lower()}%"]
        contrasts = []
        seen = set()
        notes = []
        for row in con.execute(sql, params).fetchall():
            oa_id, nct, pv, lo, hi, study_title, arms, _ = row
            parts = [p.strip() for p in (arms or "").split("||")]
            if len(parts) != 2:
                continue
            t1, t2 = classify_node(parts[0], nodes), classify_node(parts[1], nodes)
            if not (t1 and t2) or t1 == t2:
                continue
            try:
                hr, clo, chi = float(pv), float(lo), float(hi)
            except (TypeError, ValueError):
                continue
            if not (hr > 0 and clo > 0 and chi > 0 and clo < chi):
                continue
            key = (nct, frozenset((t1, t2)))
            if key in seen:
                continue
            seen.add(key)
            yi = math.log(hr)
            sei = (math.log(chi) - math.log(clo)) / (2 * Z95)
            if sei <= 0:
                continue
            contrasts.append({
                "nct": nct, "study": study_title or nct,
                "t1": t1, "t2": t2, "t1_label": parts[0], "t2_label": parts[1],
                "hr": hr, "lci": clo, "uci": chi, "yi": yi, "sei": sei,
                "source_outcome_analysis_id": str(oa_id),
            })
        treatments = sorted({c["t1"] for c in contrasts} | {c["t2"] for c in contrasts})
        return {"contrasts": contrasts, "treatments": treatments,
                "provenance": prov.to_dict(), "condition": condition,
                "outcome": ", ".join(outcome_like), "notes": notes}
    finally:
        if owns:
            con.close()


__all__ = ["extract_contrasts", "classify_node"]
