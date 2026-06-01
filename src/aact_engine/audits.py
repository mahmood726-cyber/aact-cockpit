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
                    "into one family and some records remain in a broad other bucket. Families also differ "
                    "in study phase, so early-phase-heavy areas such as healthy-volunteer studies look "
                    "quieter partly because such trials rarely post efficacy results. Results visibility "
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
                    "study was legally an applicable clinical trial under FDAAA 801. Era differences also "
                    "partly reflect time since completion, since older cohorts have had longer to post "
                    "results, so this is not a clean policy effect."),
    }


# --------------------------------------------------------------------------- #
# Audit 4 — probable ACT / FDAAA debt
# --------------------------------------------------------------------------- #
def fdaaa_debt(con) -> dict:
    cut = _snapshot_year(con) - 2
    era = (f"CASE WHEN {_COMP_YEAR} < 2017 THEN '1 Pre-Final-Rule (<2017)' "
           f"ELSE '2 Final-Rule era (2017+)' END")
    # FDA-regulated drug/device interventional study = conservative FDAAA-applicability
    # proxy. is_us_export is deliberately NOT used: in AACT it flags products EXPORTED
    # from the US for study abroad (~3% of trials), not US-located trials, so it cannot
    # stand in for U.S. nexus. True U.S. location needs the facilities table (not ingested).
    elig = (f"lower(s.study_type) = 'interventional' AND s.overall_status IN {_CLOSED} "
            f"AND ({_OLDER.format(cut=cut)}) "
            f"AND (s.is_fda_regulated_drug = 't' OR s.is_fda_regulated_device = 't')")
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
    findings = [f"{n_debt:,} FDA-regulated studies still carry no posted results, "
                f"covering {debt_enroll:,} enrolled participants."]
    if groups:
        findings.append(f"No-results rate is {groups[0]['metrics']['no_results_pct']}% in "
                        f"{groups[0]['label']}" + (f" versus {groups[-1]['metrics']['no_results_pct']}% in "
                        f"{groups[-1]['label']}." if len(groups) > 1 else "."))
    return {
        "kind": "audit", "audit_id": "ctgov-probable-act-fdaaa-debt",
        "title": "FDA-regulated reporting debt",
        "source_repo": "ctgov-probable-act-fdaaa-debt",
        "source_url": _SRC + "ctgov-probable-act-fdaaa-debt",
        "snapshot_date": con.execute("SELECT snapshot_date FROM _meta LIMIT 1").fetchone()[0],
        "provenance": _provenance(con).to_dict(),
        "question": ("How large is the FDA-regulated reporting backlog among older closed "
                     "ClinicalTrials.gov studies?"),
        "estimand": "No-results rate among FDA-regulated interventional studies, by policy era",
        "scope": {"n_eligible": n_elig, "n_debt": n_debt, "debt_enrollment": debt_enroll,
                  "definition": (f"closed interventional studies first posted in {cut} or earlier that are "
                                 "FDA-regulated (drug or device) — a conservative proxy for FDAAA 801 "
                                 "applicability")},
        "groups": groups, "primary_metric": "no_results_pct",
        "metric_order": ["no_results_pct", "ghost_pct", "visible_pct"],
        "metric_labels": _METRIC_LABELS, "findings": findings,
        "caveats": ("FDA-regulated status is a conservative proxy for FDAAA 801 applicability, not a legal "
                    "determination; U.S. nexus is not established here because AACT's export flag denotes "
                    "products studied abroad, not U.S.-located trials, and facility locations are not in "
                    "this warehouse. Ghost-protocol closely tracks no-results because disposition records "
                    "are rarely populated."),
    }


# --------------------------------------------------------------------------- #
# study_references link signals (AACT reference_type)
#   result     = sponsor-submitted CT.gov publication link  -> "linked"
#   derived    = PubMed paper auto-indexed to the NCT        -> external trail
#   background = background citation
# --------------------------------------------------------------------------- #
def _has_ref(kind: str) -> str:
    return (f"EXISTS (SELECT 1 FROM study_references r WHERE r.nct_id = s.nct_id "
            f"AND lower(r.reference_type) = '{kind}')")


def _nolink_elig(cut: int) -> str:
    return (f"lower(s.study_type) = 'interventional' AND s.overall_status IN {_CLOSED} "
            f"AND ({_OLDER.format(cut=cut)}) AND NOT {_has_ref('result')}")


def _live_sample(con, elig: str, k: int = 60) -> list[dict]:
    """A deterministic no-link NCT sub-sample (with AACT's own derived-link flag)
    that the capsule re-checks live against PubMed + Europe PMC. ORDER BY hash is
    stable across runs, so the embedded sample is reproducible."""
    rows = con.execute(f"""
        SELECT s.nct_id,
               coalesce((SELECT max(sp.agency_class) FROM sponsors sp
                         WHERE sp.nct_id = s.nct_id AND sp.lead_or_collaborator = 'lead'),
                        '(unspecified)') AS cls,
               {_has_ref('derived')} AS aact_derived
        FROM studies s WHERE {elig}
        ORDER BY hash(s.nct_id) LIMIT {k}
    """).fetchall()
    return [{"nct_id": str(n), "sponsor_class": str(c), "aact_derived": bool(d)}
            for n, c, d in rows]


# --------------------------------------------------------------------------- #
# Audit 5 — publication undercount: external PubMed trail among no-link studies
# --------------------------------------------------------------------------- #
def publication_undercount(con) -> dict:
    cut = _snapshot_year(con) - 2
    elig = _nolink_elig(cut)
    rows = con.execute(f"""
        WITH e AS (
            SELECT s.nct_id,
                   coalesce((SELECT max(sp.agency_class) FROM sponsors sp
                             WHERE sp.nct_id = s.nct_id AND sp.lead_or_collaborator = 'lead'),
                            '(unspecified)') AS cls,
                   s.results_first_posted_date AS rfp,
                   {_has_ref('derived')} AS has_derived
            FROM studies s WHERE {elig})
        SELECT cls, count(*) AS n,
               round(100.0*avg(CASE WHEN has_derived THEN 1 ELSE 0 END), 1) AS trail,
               round(100.0*avg(CASE WHEN has_derived AND rfp IS NULL THEN 1 ELSE 0 END), 1) AS ext_only
        FROM e GROUP BY 1 ORDER BY n DESC
    """).fetchall()
    groups = [{"label": str(c), "n": int(n),
               "metrics": {"pubmed_trail_pct": _fl(t), "external_only_pct": _fl(eo)}}
              for c, n, t, eo in rows if c is not None]
    n_elig = sum(g["n"] for g in groups)
    overall = con.execute(f"""
        SELECT round(100.0*avg(CASE WHEN {_has_ref('derived')} THEN 1 ELSE 0 END), 1)
        FROM studies s WHERE {elig}
    """).fetchone()[0]
    by = {g["label"]: g for g in groups if g["n"] >= 200}
    top = max(by.values(), key=lambda x: x["metrics"]["pubmed_trail_pct"]) if by else None
    findings = [f"{float(overall):.1f}% of no-link studies still carry an external PubMed trail "
                f"(an auto-indexed paper citing the NCT)."]
    if top:
        findings.append(f"{top['label']} no-link studies are best covered "
                        f"({top['metrics']['pubmed_trail_pct']}% with a PubMed trail).")
    return {
        "kind": "audit", "audit_id": "ctgov-publication-undercount-audit",
        "title": "Publication undercount audit",
        "source_repo": "ctgov-publication-undercount-audit",
        "source_url": _SRC + "ctgov-publication-undercount-audit",
        "snapshot_date": con.execute("SELECT snapshot_date FROM _meta LIMIT 1").fetchone()[0],
        "provenance": _provenance(con).to_dict(),
        "question": ("How often do ClinicalTrials.gov records with no linked publication still carry an "
                     "external PubMed trail indexed to the NCT identifier?"),
        "estimand": "External PubMed-trail rate among no-link studies, by lead-sponsor class",
        "method_sentence": ("A study counts as no-link when it has no sponsor-submitted result reference, and "
                            "an external trail means an auto-indexed PubMed reference of derived type cites its "
                            "registry identifier."),
        "scope": {"n_eligible": n_elig,
                  "definition": (f"closed interventional studies first posted in {cut} or earlier that carry "
                                 "no sponsor-submitted ClinicalTrials.gov result publication link")},
        "live_sample": _live_sample(con, elig), "live_sample_size": 60,
        "live_note": ("Live cross-check re-queries PubMed (NCT secondary-source ID) and Europe PMC for "
                      "this deterministic sub-sample; it is not part of the certified baseline."),
        "groups": groups, "primary_metric": "pubmed_trail_pct",
        "metric_order": ["pubmed_trail_pct", "external_only_pct"],
        "metric_labels": {"pubmed_trail_pct": "external PubMed trail (derived link)",
                          "external_only_pct": "external publication only (no posted results)"},
        "findings": findings,
        "caveats": ("This warehouse-native reproduction uses AACT pre-indexed derived PubMed links, which are "
                    "more complete than the original paper's live identifier-based PubMed search, so the trail "
                    "rate is much higher than the published 1.2 percent; it cannot capture papers omitting the "
                    "NCT identifier."),
    }


# --------------------------------------------------------------------------- #
# Audit 6 — publication index gap: real silence vs indexing/linkage rescue
# --------------------------------------------------------------------------- #
def publication_index_gap(con) -> dict:
    cut = _snapshot_year(con) - 2
    elig = _nolink_elig(cut)
    rows = con.execute(f"""
        WITH e AS (
            SELECT s.nct_id, {_has_ref('derived')} AS d, {_has_ref('background')} AS b
            FROM studies s WHERE {elig})
        SELECT CASE WHEN d THEN '1 PubMed-indexed (derived link)'
                    WHEN b THEN '2 Background-only reference'
                    ELSE '3 Fully silent (no reference)' END AS tier,
               count(*) AS n
        FROM e GROUP BY 1 ORDER BY 1
    """).fetchall()
    total = sum(int(n) for _, n in rows) or 1
    groups = [{"label": str(t)[2:], "n": int(n),
               "metrics": {"share_of_nolink_pct": round(100.0 * int(n) / total, 1)}}
              for t, n in rows]
    by = {g["label"]: g for g in groups}
    rescue = by.get("PubMed-indexed (derived link)", {}).get("metrics", {}).get("share_of_nolink_pct", 0)
    silent = by.get("Fully silent (no reference)", {}).get("metrics", {}).get("share_of_nolink_pct", 0)
    findings = [f"PubMed indexing rescues {rescue}% of no-link studies, "
                f"while {silent}% are fully silent with no reference of any type."]
    return {
        "kind": "audit", "audit_id": "ctgov-publication-index-gap",
        "title": "Publication index gap",
        "source_repo": "ctgov-publication-index-gap",
        "source_url": _SRC + "ctgov-publication-index-gap",
        "snapshot_date": con.execute("SELECT snapshot_date FROM _meta LIMIT 1").fetchone()[0],
        "provenance": _provenance(con).to_dict(),
        "question": ("How much of ClinicalTrials.gov publication-link missingness is real silence versus an "
                     "indexing and linkage gap rescuable through external references?"),
        "estimand": "Share of no-link studies by best available external-reference tier",
        "method_sentence": ("Each no-link study was placed in one mutually exclusive tier by its best available "
                            "external reference, namely an indexed PubMed derived link, a background-only citation, "
                            "or no reference at all."),
        "scope": {"n_eligible": total,
                  "definition": (f"closed interventional studies first posted in {cut} or earlier with no "
                                 "sponsor-submitted result publication link, partitioned by external-reference tier")},
        "live_sample": _live_sample(con, elig), "live_sample_size": 60,
        "live_note": ("Live cross-check re-queries PubMed (NCT secondary-source ID) and Europe PMC for "
                      "this deterministic sub-sample; it is not part of the certified baseline."),
        "groups": groups, "primary_metric": "share_of_nolink_pct",
        "metric_order": ["share_of_nolink_pct"],
        "metric_labels": {"share_of_nolink_pct": "share of no-link studies"},
        "findings": findings,
        "caveats": ("This warehouse-native reproduction substitutes AACT indexed references (derived, background) "
                    "for the original paper's live PubMed and Europe PMC identifier searches, so the indexing-gap "
                    "split differs from the published Europe PMC rescue figures and cannot confirm that each "
                    "linked paper fully reports the registered study."),
    }


AUDITS = {
    "ctgov-stopped-trial-disclosure-gap": stopped_trial_disclosure_gap,
    "ctgov-condition-hiddenness-map": condition_hiddenness_map,
    "ctgov-rule-era-reporting-gap": rule_era_reporting_gap,
    "ctgov-probable-act-fdaaa-debt": fdaaa_debt,
    "ctgov-publication-undercount-audit": publication_undercount,
    "ctgov-publication-index-gap": publication_index_gap,
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
