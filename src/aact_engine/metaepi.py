"""Registry-wide meta-epidemiology over the WHOLE AACT outcome_analyses corpus.

Not a single-question meta-analysis — a characterization of the entire reported
evidence base: how often registered ratio analyses are statistically significant,
how that varies by lead-sponsor class, and the small-study ("winner's curse")
relationship between trial size and reported effect magnitude. Deterministic SQL
aggregates; carries snapshot provenance.
"""
from __future__ import annotations

import math

from .query import open_warehouse, _provenance

# ratio measures whose CI can be tested against the null of 1
_RATIO = ("lower(oa.param_type) LIKE '%hazard ratio%' "
          "OR lower(oa.param_type) LIKE '%odds ratio%' "
          "OR lower(oa.param_type) LIKE '%risk ratio%' "
          "OR lower(oa.param_type) LIKE '%relative risk%'")
# usable = positive estimate + positive ordered CI, within a sane range
_USABLE = (f"({_RATIO}) "
           "AND TRY_CAST(oa.param_value AS DOUBLE) > 0 "
           "AND TRY_CAST(oa.ci_lower_limit AS DOUBLE) > 0 "
           "AND TRY_CAST(oa.ci_upper_limit AS DOUBLE) > 0 "
           "AND TRY_CAST(oa.ci_lower_limit AS DOUBLE) < TRY_CAST(oa.ci_upper_limit AS DOUBLE) "
           "AND TRY_CAST(oa.param_value AS DOUBLE) BETWEEN 0.01 AND 100 "
           "AND TRY_CAST(oa.ci_upper_limit AS DOUBLE) < 100")


def registry_atlas(con=None, db_path=None) -> dict:
    """Compute the registry meta-epidemiology atlas. Returns a JSON-able dict."""
    owns = con is None
    if owns:
        con = open_warehouse(db_path)
    try:
        prov = _provenance(con, db_path)

        scope = con.execute(f"""
            WITH u AS (SELECT TRY_CAST(oa.param_value AS DOUBLE) hr,
                              TRY_CAST(oa.ci_lower_limit AS DOUBLE) lo,
                              TRY_CAST(oa.ci_upper_limit AS DOUBLE) hi
                       FROM outcome_analyses oa WHERE {_USABLE})
            SELECT count(*),
                   count(*) FILTER (WHERE hi < 1 OR lo > 1),
                   median(ln(hr)),
                   count(*) FILTER (WHERE hr < 1),
                   count(DISTINCT 1)
            FROM u
        """).fetchone()
        n, n_sig, med_log, n_low, _ = scope
        n_trials = con.execute(f"""
            SELECT count(DISTINCT oa.nct_id) FROM outcome_analyses oa WHERE {_USABLE}
        """).fetchone()[0]

        by_sponsor = []
        for cls, cnt, sig in con.execute(f"""
            WITH u AS (SELECT oa.nct_id, TRY_CAST(oa.ci_lower_limit AS DOUBLE) lo,
                              TRY_CAST(oa.ci_upper_limit AS DOUBLE) hi
                       FROM outcome_analyses oa WHERE {_USABLE})
            SELECT coalesce(sp.agency_class,'(unspecified)'), count(*),
                   count(*) FILTER (WHERE hi < 1 OR lo > 1)
            FROM u JOIN sponsors sp ON sp.nct_id = u.nct_id AND sp.lead_or_collaborator = 'lead'
            GROUP BY 1 HAVING count(*) >= 50 ORDER BY count(*) DESC
        """).fetchall():
            by_sponsor.append({"sponsor_class": cls, "n": cnt, "n_sig": sig,
                               "pct_sig": round(100.0 * sig / cnt, 1)})

        by_size = []
        for b, cnt, mae, msig in con.execute(f"""
            WITH u AS (SELECT TRY_CAST(oa.param_value AS DOUBLE) hr,
                              TRY_CAST(oa.ci_lower_limit AS DOUBLE) lo,
                              TRY_CAST(oa.ci_upper_limit AS DOUBLE) hi,
                              TRY_CAST(s.enrollment AS DOUBLE) enr
                       FROM outcome_analyses oa JOIN studies s ON s.nct_id = oa.nct_id
                       WHERE {_USABLE} AND TRY_CAST(s.enrollment AS DOUBLE) > 0)
            SELECT CASE WHEN enr<100 THEN '<100' WHEN enr<500 THEN '100-499'
                        WHEN enr<2000 THEN '500-1999' ELSE '>=2000' END,
                   count(*), median(abs(ln(hr))),
                   100.0*count(*) FILTER (WHERE hi<1 OR lo>1)/count(*)
            FROM u GROUP BY 1
            ORDER BY CASE WHEN min(enr)<100 THEN 1 WHEN min(enr)<500 THEN 2
                          WHEN min(enr)<2000 THEN 3 ELSE 4 END
        """).fetchall():
            by_size.append({"bin": b, "n": cnt, "median_abs_logeffect": round(mae, 4),
                            "pct_sig": round(msig, 1)})

        # histogram of log effects, bins of 0.2 from -2 to 2
        hist = []
        for c, cnt in con.execute(f"""
            WITH u AS (SELECT TRY_CAST(oa.param_value AS DOUBLE) hr
                       FROM outcome_analyses oa WHERE {_USABLE}),
                 g AS (SELECT ln(hr) le FROM u WHERE hr > 0)
            SELECT round(le/0.2)*0.2 AS center, count(*)
            FROM g WHERE le BETWEEN -2 AND 2 GROUP BY 1 ORDER BY 1
        """).fetchall():
            hist.append({"center": round(c, 2), "count": cnt})

        return {
            "kind": "atlas", "snapshot_date": prov.snapshot_date,
            "provenance": prov.to_dict(),
            "scope": {"n_analyses": n, "n_trials": n_trials, "n_significant": n_sig,
                      "pct_significant": round(100.0 * n_sig / n, 1),
                      "median_effect": round(math.exp(med_log), 3),
                      "pct_favor_low": round(100.0 * n_low / n, 1)},
            "by_sponsor": by_sponsor, "by_size": by_size, "effect_hist": hist,
        }
    finally:
        if owns:
            con.close()


__all__ = ["registry_atlas"]
