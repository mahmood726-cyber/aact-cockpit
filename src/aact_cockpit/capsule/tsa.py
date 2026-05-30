"""Trial Sequential Analysis (TSA) / cumulative meta-analysis engine.

Reuses the validated pairwise pooling (pooling.pool) but accumulates trials in
chronological order and overlays O'Brien-Fleming monitoring boundaries against a
diversity-adjusted Required Information Size (RIS).

Formulas follow the user's advanced-stats.md TSA rules:
  - O'Brien-Fleming boundary:  Z_bound(t_k) = z_{1-alpha/2} / sqrt(t_k)
  - Heterogeneity design effect (NOT cluster):
        DEFF = 1 + tau^2 * ( (sum 1/v_i^2) / (sum 1/v_i)^2 * k  -  1 )
  - Futility is non-binding (we apply the efficacy boundary only).

Information is statistical information I_k = 1/se_k^2 from the cumulative
random-effects pool. RIS in information units:
        I_RIS = ((z_{1-alpha/2} + z_{1-beta}) / mu)^2  * DEFF
with mu = anticipated |log effect| (post-hoc default = |observed pooled| with a
floor so a near-null observed effect does not blow RIS up to infinity).
"""
from __future__ import annotations

import math

from .pooling import pool, Z

# standard-normal quantiles
Z_ALPHA_2 = 1.959963984540054   # z_{0.975}, two-sided alpha=0.05
Z_BETA_80 = 0.8416212335729143  # z_{0.80}, power 0.80
MU_FLOOR = abs(math.log(0.90))  # anticipate at least a 10% RRR (avoid RIS->inf)


def _ordered(records: list[dict]) -> list[dict]:
    """Chronological order; deterministic tie-break by nct."""
    def key(s):
        return (s.get("year") if s.get("year") is not None else 9999, str(s.get("nct", "")))
    return sorted(records, key=key)


def cumulative(records: list[dict], method: str = "PM",
               z_alpha2: float = Z_ALPHA_2, z_beta: float = Z_BETA_80,
               mu: float | None = None) -> dict:
    """Return the cumulative-MA + TSA result for a list of {nct,name,year,hr,lci,uci,inc}.

    Output keys:
      steps[]   per cumulative step: {k, year, name, est, ci_lower, ci_upper,
                                      z, info, t, obf}
      ris, deff, mu, z_alpha2, z_beta
      final_z, crossed (step index where |Z| first crosses OBF, or None)
      conclusion ('firm' | 'insufficient' | 'ris_reached_null')
    """
    items = [s for s in _ordered(records) if s.get("inc", True)]
    full = pool(items, method=method)
    if full is None or full["k"] < 2:
        return {"steps": [], "ris": None, "conclusion": "insufficient",
                "crossed": None, "k": 0}

    # within-study variances v_i for the design effect
    use = [s for s in items if _ok(s)]
    v = [((math.log(s["uci"]) - math.log(s["lci"])) / (2 * Z)) ** 2 for s in use]
    tau2 = full["tau2"]
    sw = sum(1.0 / vi for vi in v)
    sw2 = sum(1.0 / (vi * vi) for vi in v)
    k = len(v)
    # DEFF = 1 + tau^2 * ( (sum 1/v^2)/(sum 1/v)^2 * k - 1 )   (advanced-stats.md)
    deff = 1.0 + tau2 * (sw2 / (sw * sw) * k - 1.0) if sw > 0 else 1.0
    deff = max(1.0, deff)

    if mu is None:
        mu = max(abs(full["re_log"]), MU_FLOOR)
    i_ris = ((z_alpha2 + z_beta) / mu) ** 2 * deff

    steps = []
    crossed = None
    running = []
    for s in use:
        running.append(s)
        r = pool(running, method=method)
        if r is None:
            continue
        se = r["se_re"]
        info = 1.0 / (se * se)
        z = r["re_log"] / se
        t = info / i_ris if i_ris > 0 else 0.0
        obf = z_alpha2 / math.sqrt(t) if t > 0 else None  # None (not inf) -> JSON-clean payload
        step = {
            "k": len(running), "year": s.get("year"), "name": s.get("name", ""),
            "est": r["est"], "ci_lower": r["ci_lower"], "ci_upper": r["ci_upper"],
            "z": z, "info": info, "t": t, "obf": obf,
        }
        steps.append(step)
        if crossed is None and obf is not None and abs(z) >= obf:
            crossed = step["k"]

    final = steps[-1]
    if crossed is not None:
        conclusion = "firm"          # crossed the monitoring boundary -> conclusive
    elif final["t"] >= 1.0:
        conclusion = "ris_reached_null"   # enough information, boundary not crossed
    else:
        conclusion = "insufficient"  # not enough information yet

    return {
        "steps": steps, "ris": i_ris, "deff": deff, "mu": mu,
        "z_alpha2": z_alpha2, "z_beta": z_beta, "tau2": tau2,
        "final_z": final["z"], "final_t": final["t"], "crossed": crossed,
        "conclusion": conclusion, "k": k, "method": method,
    }


def _ok(s) -> bool:
    try:
        return (s["hr"] > 0 and s["lci"] > 0 and s["uci"] > 0
                and s["lci"] <= s["hr"] <= s["uci"])
    except (KeyError, TypeError):
        return False


__all__ = ["cumulative", "Z_ALPHA_2", "Z_BETA_80"]
