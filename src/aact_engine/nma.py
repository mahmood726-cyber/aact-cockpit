"""Network meta-analysis contrast extraction from AACT.

Builds oriented log-effect contrasts (treat1 vs treat2, experimental vs
comparator) for a condition + outcome, mapping each arm to a treatment node via
a caller-supplied keyword map. One contrast per (trial, edge), deterministic
(lowest outcome_analysis id). Carries snapshot provenance.
"""
from __future__ import annotations

import math
import re
from statistics import median

from .effects import Z95
from .guards import assert_columns_exist
from .query import open_warehouse, _provenance

_YEAR_RE = re.compile(r"(\d{4})")


def classify_node(title: str, nodes: dict[str, list[str]]) -> str | None:
    """Map an arm title to a treatment node by WORD-BOUNDARY keyword match (so a
    drug name embedded in another token cannot mis-route the contrast)."""
    return (_classify_kw(title, nodes) or (None, None))[0]


def _classify_kw(title: str, nodes: dict[str, list[str]]):
    """Like classify_node but also returns WHICH keyword matched — the underlying
    agent lumped into the class node, for the transitivity assessment."""
    tl = (title or "").lower()
    for name, kws in nodes.items():
        for k in kws:
            if re.search(r"\b" + re.escape(k.lower()) + r"\b", tl):
                return name, k.lower()
    return None


def _year_of(start_date):
    if not start_date:
        return None
    m = _YEAR_RE.search(str(start_date))
    return int(m.group(1)) if m else None


def assess_transitivity(contrasts: list[dict], treatments: list[str]) -> dict:
    """Surface the transitivity assumption for an AACT class-node NMA: which agents
    each class node lumps, and whether edges differ sharply in era or trial size
    (effect-modifiers that can break the indirect-comparison assumption). This is a
    clinical-comparability screen; statistical inconsistency (Bucher) is separate."""
    edges: dict = {}
    node_agents: dict = {}
    node_n: dict = {}
    for c in contrasts:
        ek = frozenset((c["t1"], c["t2"]))
        e = edges.setdefault(ek, {"years": [], "enrolls": []})
        if c.get("year"):
            e["years"].append(c["year"])
        if c.get("enrollment"):
            e["enrolls"].append(c["enrollment"])
        for node, agent in ((c["t1"], c.get("agent1")), (c["t2"], c.get("agent2"))):
            node_agents.setdefault(node, set())
            if agent:
                node_agents[node].add(agent)
            node_n[node] = node_n.get(node, 0) + 1
    edge_year = {k: median(v["years"]) for k, v in edges.items() if v["years"]}
    edge_enr = {k: median(v["enrolls"]) for k, v in edges.items() if v["enrolls"]}
    year_span = (max(edge_year.values()) - min(edge_year.values())) if len(edge_year) >= 2 else 0.0
    enr_ratio = (max(edge_enr.values()) / min(edge_enr.values())
                 if len(edge_enr) >= 2 and min(edge_enr.values()) > 0 else 1.0)
    flags = []
    if year_span >= 15:
        flags.append(f"era heterogeneity: edge median start-years span {year_span:.0f} years")
    if enr_ratio >= 10:
        flags.append(f"size disparity: edge median enrolment differs {enr_ratio:.0f}-fold across edges")
    for node in treatments:
        n_ag = len(node_agents.get(node, set()))
        if n_ag >= 4:
            flags.append(f"class lumping: node '{node}' aggregates {n_ag} distinct agents")
    by_node = [{"node": n, "n_contrasts": node_n.get(n, 0),
                "agents": sorted(node_agents.get(n, set()))} for n in treatments]
    return {"by_node": by_node, "year_span": round(year_span, 1),
            "enroll_ratio": round(enr_ratio, 1), "flags": flags,
            "assessment": "warn" if flags else "pass"}


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
                   s.start_date AS start_date, s.enrollment AS enrollment,
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
            GROUP BY oa.id, oa.nct_id, oa.param_value, oa.ci_lower_limit, oa.ci_upper_limit,
                     study_title, s.start_date, s.enrollment
            HAVING count(rg.id) = 2
            ORDER BY oa.nct_id, CAST(oa.id AS BIGINT)
        """
        params = [f"%{condition.lower()}%"] + [f"%{o.lower()}%" for o in outcome_like] + [f"%{measure_like.lower()}%"]
        contrasts = []
        seen = set()
        notes = []
        for row in con.execute(sql, params).fetchall():
            oa_id, nct, pv, lo, hi, study_title, start_date, enrollment, arms, _ = row
            parts = [p.strip() for p in (arms or "").split("||")]
            if len(parts) != 2:
                continue
            c1, c2 = _classify_kw(parts[0], nodes), _classify_kw(parts[1], nodes)
            t1, agent1 = c1 if c1 else (None, None)
            t2, agent2 = c2 if c2 else (None, None)
            if not (t1 and t2) or t1 == t2:
                continue
            try:
                enr = float(enrollment)
            except (TypeError, ValueError):
                enr = None
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
                "year": _year_of(start_date), "enrollment": enr,
                "agent1": agent1, "agent2": agent2,
                "source_outcome_analysis_id": str(oa_id),
            })
        treatments = sorted({c["t1"] for c in contrasts} | {c["t2"] for c in contrasts})
        return {"contrasts": contrasts, "treatments": treatments,
                "provenance": prov.to_dict(), "condition": condition,
                "outcome": ", ".join(outcome_like), "notes": notes,
                "transitivity": assess_transitivity(contrasts, treatments)}
    finally:
        if owns:
            con.close()


__all__ = ["extract_contrasts", "classify_node", "assess_transitivity"]
