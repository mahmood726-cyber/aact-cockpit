"""Registry-wide ct.gov disclosure/reporting audits over the WHOLE AACT corpus.

Reproduces a family of the user's standalone ct.gov E156 audits as deterministic
SQL over the warehouse: how disclosure debt (no-results, ghost protocols) varies
by final status, condition family, policy era, and FDA-regulated status. Each
returns a normalized "audit-result" dict consumed by generate_audit_capsule.

These are reproductions on the warehouse snapshot; exact numbers differ from the
originally published runs (different registry snapshot) but the analysis is the
same. Operational definitions are stated in each result's `scope.definition`.
"""
from __future__ import annotations

from .query import open_warehouse, _provenance

# closed / terminal interventional statuses (uppercase in AACT v2 flat files)
_CLOSED = "('COMPLETED','TERMINATED','WITHDRAWN','SUSPENDED')"
_STOPPED = "('TERMINATED','WITHDRAWN','SUSPENDED')"
_FIRST_YEAR = "TRY_CAST(substr(s.study_first_posted_date,1,4) AS INTEGER)"
_COMP_YEAR = "TRY_CAST(substr(s.completion_date,1,4) AS INTEGER)"
# a study is "older" when its registration window allows a 2-year reporting lag
_OLDER = f"{_FIRST_YEAR} IS NOT NULL AND {_FIRST_YEAR} <= {{cut}}"

# disclosure metrics (all booleans aggregated as 100*avg)
_NO_RESULTS = "s.results_first_posted_date IS NULL"
_GHOST = "s.results_first_posted_date IS NULL AND s.disposition_first_posted_date IS NULL"
_REASON_MISSING = (f"s.overall_status IN {_STOPPED} AND "
                   "(s.why_stopped IS NULL OR trim(s.why_stopped) = '')")
_VISIBLE = "s.results_first_posted_date IS NOT NULL"

_SRC = "https://github.com/mahmood726-cyber/"


def _snapshot_year(con) -> int:
    d = con.execute("SELECT snapshot_date FROM _meta LIMIT 1").fetchone()[0]
    try:
        return int(str(d)[:4])
    except (ValueError, TypeError):
        return 2026


def _pct(con, where_eligible: str, group_expr: str, params=None):
    """Return [(label, n, no_results_pct, ghost_pct, reason_missing_pct, visible_pct)]
    grouped by group_expr over the eligible set. Deterministic order by n desc."""
    sql = f"""
        SELECT {group_expr} AS g, count(*) AS n,
               round(100.0*avg(CASE WHEN {_NO_RESULTS} THEN 1 ELSE 0 END), 1),
               round(100.0*avg(CASE WHEN {_GHOST} THEN 1 ELSE 0 END), 1),
               round(100.0*avg(CASE WHEN {_REASON_MISSING} THEN 1 ELSE 0 END), 1),
               round(100.0*avg(CASE WHEN {_VISIBLE} THEN 1 ELSE 0 END), 1)
        FROM studies s
        WHERE {where_eligible}
        GROUP BY 1 ORDER BY n DESC
    """
    return con.execute(sql, params or []).fetchall()


_METRIC_LABELS = {
    "no_results_pct": "no results posted",
    "ghost_pct": "ghost protocol (no results, no disposition)",
    "reason_missing_pct": "stop-reason field missing",
    "visible_pct": "results visible",
}


def _fl(x):
    """Coerce DuckDB numerics (DECIMAL/DOUBLE) to plain float for JSON."""
    return None if x is None else float(x)


def _rows_to_groups(rows, keep=None):
    groups = []
    for g, n, nr, gh, rm, vis in rows:
        if g is None:
            continue
        groups.append({"label": str(g).title() if isinstance(g, str) else str(g),
                       "n": int(n), "metrics": {"no_results_pct": _fl(nr), "ghost_pct": _fl(gh),
                                                "reason_missing_pct": _fl(rm), "visible_pct": _fl(vis)}})
    if keep:
        groups = [x for x in groups if x["label"] in keep] or groups
    return groups


# --------------------------------------------------------------------------- #
# Audit 1 — stopped-trial disclosure gap
# --------------------------------------------------------------------------- #
def stopped_trial_disclosure_gap(con) -> dict:
    cut = _snapshot_year(con) - 2
    elig = (f"lower(s.study_type) = 'interventional' AND s.overall_status IN {_CLOSED} "
            f"AND ({_OLDER.format(cut=cut)})")
    rows = _pct(con, elig, "s.overall_status")
    groups = _rows_to_groups(rows)
    order = ["Completed", "Terminated", "Withdrawn", "Suspended"]
    groups.sort(key=lambda x: order.index(x["label"]) if x["label"] in order else 99)
    n_elig = sum(g["n"] for g in groups)
    by = {g["label"]: g for g in groups}
    findings = []
    if "Withdrawn" in by:
        findings.append(f"Withdrawn studies reach {by['Withdrawn']['metrics']['no_results_pct']}% "
                        f"no-results and {by['Withdrawn']['metrics']['ghost_pct']}% ghost-protocol.")
    if "Completed" in by and "Terminated" in by:
        findings.append(f"Completed studies sit at {by['Completed']['metrics']['no_results_pct']}% "
                        f"no-results versus {by['Terminated']['metrics']['no_results_pct']}% for terminated.")
    return {
        "kind": "audit", "audit_id": "ctgov-stopped-trial-disclosure-gap",
        "title": "Stopped-trial disclosure gap",
        "source_repo": "ctgov-stopped-trial-disclosure-gap",
        "source_url": _SRC + "ctgov-stopped-trial-disclosure-gap",
        "snapshot_date": con.execute("SELECT snapshot_date FROM _meta LIMIT 1").fetchone()[0],
        "provenance": _provenance(con).to_dict(),
        "question": ("How much worse do stopped trials look on ClinicalTrials.gov than completed "
                     "trials once older closed interventional studies are grouped by final status?"),
        "estimand": "No-results and ghost-protocol rates across final-status groups",
        "scope": {"n_eligible": n_elig,
                  "definition": (f"interventional studies with a closed final status "
                                 f"(completed/terminated/withdrawn/suspended) first posted in {cut} or earlier")},
        "groups": groups, "primary_metric": "no_results_pct",
        "metric_order": ["no_results_pct", "ghost_pct", "reason_missing_pct"],
        "metric_labels": _METRIC_LABELS, "findings": findings,
        "caveats": ("Final-status labels and missing reason fields are registry entries and do not "
                    "adjudicate operational history or legal reporting obligations."),
    }


# --------------------------------------------------------------------------- #
# Audit 2 — condition hiddenness map
# --------------------------------------------------------------------------- #
_FAMILY_CASE = """
CASE
 WHEN t LIKE '%healthy%' THEN 'Healthy volunteer'
 WHEN t LIKE '%cancer%' OR t LIKE '%tumor%' OR t LIKE '%tumour%' OR t LIKE '%carcinoma%'
   OR t LIKE '%oncolog%' OR t LIKE '%neoplasm%' OR t LIKE '%leukemia%' OR t LIKE '%lymphoma%'
   OR t LIKE '%melanoma%' OR t LIKE '%sarcoma%' THEN 'Oncology'
 WHEN t LIKE '%heart%' OR t LIKE '%cardiac%' OR t LIKE '%cardiovascular%' OR t LIKE '%coronary%'
   OR t LIKE '%hypertension%' OR t LIKE '%atrial%' OR t LIKE '%stroke%' OR t LIKE '%vascular%' THEN 'Cardiovascular'
 WHEN t LIKE '%infection%' OR t LIKE '%infectious%' OR t LIKE '%hiv%' OR t LIKE '%hepatitis%'
   OR t LIKE '%covid%' OR t LIKE '%sars%' OR t LIKE '%tuberculosis%' OR t LIKE '%malaria%'
   OR t LIKE '%sepsis%' OR t LIKE '%influenza%' THEN 'Infectious disease'
 WHEN t LIKE '%diabet%' OR t LIKE '%obesity%' OR t LIKE '%metabolic%' OR t LIKE '%glycemic%'
   OR t LIKE '%lipid%' OR t LIKE '%cholesterol%' OR t LIKE '%thyroid%' THEN 'Metabolic / endocrine'
 WHEN t LIKE '%gastro%' OR t LIKE '%crohn%' OR t LIKE '%colitis%' OR t LIKE '%bowel%'
   OR t LIKE '%hepatic%' OR t LIKE '%liver%' OR t LIKE '%pancrea%' THEN 'Gastrointestinal'
 WHEN t LIKE '%alzheimer%' OR t LIKE '%parkinson%' OR t LIKE '%epilep%' OR t LIKE '%sclerosis%'
   OR t LIKE '%neuro%' OR t LIKE '%migraine%' OR t LIKE '%dementia%' THEN 'Neurology'
 WHEN t LIKE '%asthma%' OR t LIKE '%copd%' OR t LIKE '%pulmonary%' OR t LIKE '%respiratory%'
   OR t LIKE '%lung%' THEN 'Respiratory'
 WHEN t LIKE '%depress%' OR t LIKE '%anxiety%' OR t LIKE '%schizophreni%' OR t LIKE '%psychiat%'
   OR t LIKE '%bipolar%' THEN 'Mental health'
 WHEN t LIKE '%arthritis%' OR t LIKE '%osteo%' OR t LIKE '%musculoskeletal%' OR t LIKE '%joint%' THEN 'Musculoskeletal'
 ELSE 'Other / unmapped' END
"""


def condition_hiddenness_map(con) -> dict:
    cut = _snapshot_year(con) - 2
    # per-study classification text = title + aggregated condition names
    base = f"""
        WITH txt AS (
            SELECT s.nct_id,
                   lower(coalesce(s.official_title, s.brief_title, '') || ' ' ||
                         coalesce((SELECT string_agg(c.downcase_name, ' ')
                                   FROM conditions c WHERE c.nct_id = s.nct_id), '')) AS t,
                   s.results_first_posted_date, s.disposition_first_posted_date, s.overall_status, s.why_stopped
            FROM studies s
            WHERE lower(s.study_type) = 'interventional' AND s.overall_status IN {_CLOSED}
              AND ({_OLDER.format(cut=cut)})
        )
        SELECT {_FAMILY_CASE} AS g, count(*) n,
               round(100.0*avg(CASE WHEN results_first_posted_date IS NULL THEN 1 ELSE 0 END),1),
               round(100.0*avg(CASE WHEN results_first_posted_date IS NULL
                                     AND disposition_first_posted_date IS NULL THEN 1 ELSE 0 END),1),
               0.0,
               round(100.0*avg(CASE WHEN results_first_posted_date IS NOT NULL THEN 1 ELSE 0 END),1)
        FROM txt GROUP BY 1 ORDER BY n DESC
    """
    rows = con.execute(base).fetchall()
    groups = _rows_to_groups(rows)
    n_elig = sum(g["n"] for g in groups)
    named = [g for g in groups if g["label"] != "Other / unmapped"]
    findings = []
    if named:
        big = max(named, key=lambda x: x["n"])
        ghosty = max(named, key=lambda x: x["metrics"]["ghost_pct"])
        findings.append(f"{big['label']} is the largest named family ({big['n']:,} studies).")
        findings.append(f"{ghosty['label']} is the most obscured named family "
                        f"({ghosty['metrics']['ghost_pct']}% ghost-protocol).")
    return {
        "kind": "audit", "audit_id": "ctgov-condition-hiddenness-map",
        "title": "Condition hiddenness map",
        "source_repo": "ctgov-condition-hiddenness-map",
        "source_url": _SRC + "ctgov-condition-hiddenness-map",
        "snapshot_date": con.execute("SELECT snapshot_date FROM _meta LIMIT 1").fetchone()[0],
        "provenance": _provenance(con).to_dict(),
        "question": ("Which therapeutic areas look quietest on ClinicalTrials.gov once older closed "
                     "interventional studies are grouped into keyword-based condition families?"),
        "estimand": "Ghost-protocol and no-results rates by dominant condition family",
        "scope": {"n_eligible": n_elig,
                  "definition": (f"closed interventional studies first posted in {cut} or earlier, each "
                                 "assigned one dominant keyword-based condition family from title + conditions")},
        "groups": groups, "primary_metric": "ghost_pct",
        "metric_order": ["ghost_pct", "no_results_pct", "visible_pct"],
        "metric_labels": _METRIC_LABELS, "findings": findings,
        "caveats": ("Classification is keyword-based and single-label; multi-topic trials are compressed "
                    "into one family and some records remain in a broad other bucket. Results visibility "
                    "here means a posted results record, not confirmed publication linkage."),
    }


# --------------------------------------------------------------------------- #
# Audit 3 — rule-era reporting gap
# --------------------------------------------------------------------------- #
def rule_era_reporting_gap(con) -> dict:
    cut = _snapshot_year(con) - 2
    era = (f"CASE WHEN {_COMP_YEAR} < 2008 THEN '1 Pre-FDAAA (<2008)' "
           f"WHEN {_COMP_YEAR} <= 2016 THEN '2 FDAAA era (2008-2016)' "
           f"ELSE '3 Final-Rule era (2017+)' END")
    elig = (f"lower(s.study_type) = 'interventional' AND s.overall_status = 'COMPLETED' "
            f"AND {_COMP_YEAR} IS NOT NULL AND {_COMP_YEAR} <= {cut}")
    rows = _pct(con, elig, era)
    groups = _rows_to_groups(rows)
    groups.sort(key=lambda x: x["label"])
    for g in groups:                       # strip the sort-prefix digit
        g["label"] = g["label"][2:]
    n_elig = sum(g["n"] for g in groups)
    findings = []
    if len(groups) >= 2:
        findings.append(f"No-results rate runs {groups[0]['metrics']['no_results_pct']}% "
                        f"({groups[0]['label']}) to {groups[-1]['metrics']['no_results_pct']}% "
                        f"({groups[-1]['label']}).")
    return {
        "kind": "audit", "audit_id": "ctgov-rule-era-reporting-gap",
        "title": "Rule-era reporting gap",
        "source_repo": "ctgov-rule-era-reporting-gap",
        "source_url": _SRC + "ctgov-rule-era-reporting-gap",
        "snapshot_date": con.execute("SELECT snapshot_date FROM _meta LIMIT 1").fetchone()[0],
        "provenance": _provenance(con).to_dict(),
        "question": ("Does ClinicalTrials.gov results reporting differ across completed cohorts from "
                     "the pre-FDAAA, FDAAA, and Final-Rule policy eras?"),
        "estimand": "No-results and ghost-protocol rates by completion-date policy era",
        "scope": {"n_eligible": n_elig,
                  "definition": (f"completed interventional studies with a completion year of {cut} or "
                                 "earlier, binned by policy era (FDAAA 2007; Final Rule 2017)")},
        "groups": groups, "primary_metric": "no_results_pct",
        "metric_order": ["no_results_pct", "ghost_pct", "visible_pct"],
        "metric_labels": _METRIC_LABELS, "findings": findings,
        "caveats": ("Policy-era bins are completion-date proxies; they do not establish that any given "
                    "study was legally an applicable clinical trial under FDAAA 801."),
    }


# --------------------------------------------------------------------------- #
# Audit 4 — probable ACT / FDAAA debt
# --------------------------------------------------------------------------- #
def fdaaa_debt(con) -> dict:
    cut = _snapshot_year(con) - 2
    era = (f"CASE WHEN {_COMP_YEAR} < 2017 THEN '1 Pre-Final-Rule (<2017)' "
           f"ELSE '2 Final-Rule era (2017+)' END")
    # conservative proxy: FDA-regulated drug/device intervention with a US-nexus flag
    elig = (f"lower(s.study_type) = 'interventional' AND s.overall_status IN {_CLOSED} "
            f"AND ({_OLDER.format(cut=cut)}) "
            f"AND (s.is_fda_regulated_drug = 't' OR s.is_fda_regulated_device = 't') "
            f"AND s.is_us_export = 't'")
    rows = _pct(con, elig, era)
    groups = _rows_to_groups(rows)
    groups.sort(key=lambda x: x["label"])
    for g in groups:
        g["label"] = g["label"][2:]
    n_elig = sum(g["n"] for g in groups)
    # headline: probable-debt count = no-results among the eligible regulated set
    debt = con.execute(f"""
        SELECT count(*) FILTER (WHERE {_NO_RESULTS}),
               round(sum(CASE WHEN {_NO_RESULTS} THEN coalesce(TRY_CAST(s.enrollment AS BIGINT),0) ELSE 0 END))
        FROM studies s WHERE {elig}
    """).fetchone()
    n_debt, debt_enroll = debt[0], int(debt[1] or 0)
    findings = [f"{n_debt:,} probable-ACT studies still carry no posted results, "
                f"covering {debt_enroll:,} enrolled participants."]
    if groups:
        findings.append(f"No-results rate is {groups[0]['metrics']['no_results_pct']}% in "
                        f"{groups[0]['label']}" + (f" versus {groups[-1]['metrics']['no_results_pct']}% in "
                        f"{groups[-1]['label']}." if len(groups) > 1 else "."))
    return {
        "kind": "audit", "audit_id": "ctgov-probable-act-fdaaa-debt",
        "title": "Probable ACT / FDAAA reporting debt",
        "source_repo": "ctgov-probable-act-fdaaa-debt",
        "source_url": _SRC + "ctgov-probable-act-fdaaa-debt",
        "snapshot_date": con.execute("SELECT snapshot_date FROM _meta LIMIT 1").fetchone()[0],
        "provenance": _provenance(con).to_dict(),
        "question": ("How large is the likely U.S.-nexus FDA-regulated reporting backlog among older "
                     "closed ClinicalTrials.gov studies?"),
        "estimand": "No-results rate among probable applicable clinical trials, by policy era",
        "scope": {"n_eligible": n_elig, "n_debt": n_debt, "debt_enrollment": debt_enroll,
                  "definition": (f"closed interventional studies first posted in {cut} or earlier, FDA-"
                                 "regulated (drug or device) with a U.S.-export flag — a conservative "
                                 "probable-ACT proxy")},
        "groups": groups, "primary_metric": "no_results_pct",
        "metric_order": ["no_results_pct", "ghost_pct", "visible_pct"],
        "metric_labels": _METRIC_LABELS, "findings": findings,
        "caveats": ("Regulated-status and U.S.-export flags are conservative proxies for FDAAA 801 "
                    "applicability, not a legal determination; true ACT status requires case review."),
    }


AUDITS = {
    "ctgov-stopped-trial-disclosure-gap": stopped_trial_disclosure_gap,
    "ctgov-condition-hiddenness-map": condition_hiddenness_map,
    "ctgov-rule-era-reporting-gap": rule_era_reporting_gap,
    "ctgov-probable-act-fdaaa-debt": fdaaa_debt,
}


def run_audit(audit_id: str, con=None, db_path=None) -> dict:
    if audit_id not in AUDITS:
        raise KeyError(f"unknown audit {audit_id!r}; choices: {list(AUDITS)}")
    owns = con is None
    if owns:
        con = open_warehouse(db_path)
    try:
        return AUDITS[audit_id](con)
    finally:
        if owns:
            con.close()


__all__ = ["run_audit", "AUDITS"]
