"""Random-effects pooling — a Python port of the validated flagship JS engine
(F:\\E156\\flagship\\sglt2-hf-capsule.html lines 341-392).

Ported line-for-line so the Python self-audit and the capsule's live JS engine
produce identical results on identical data (the dashboard_match check asserts
this to 1e-9). Pools on the log scale; works for HR/OR/RR (log-ratio) measures.

Cross-checked against rapidmeta-finerenone/validate_living_ma_portfolio.py
pool_dl (DL estimator) within 1e-4.
"""
from __future__ import annotations

import math

Z = 1.959963984540054

# Two-sided 95% t critical values, keyed by df (matches JS T975 table).
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
        8: 2.306, 9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086, 30: 2.042}


def tcrit(df: int) -> float:
    if df <= 0:
        return Z
    if df in T975:
        return T975[df]
    for k in sorted(T975):
        if df <= k:
            return T975[k]
    return 1.962


def _wmean(y, v, t2):
    w = [1.0 / (vi + t2) for vi in v]
    sw = sum(w)
    m = sum(w[i] * y[i] for i in range(len(y))) / sw
    return w, sw, m


def _genQ(y, v, t2):
    w, sw, m = _wmean(y, v, t2)
    return sum(w[i] * (y[i] - m) ** 2 for i in range(len(y)))


def tau2_dl(y, v):
    w, sw, m = _wmean(y, v, 0)
    Q = sum(w[i] * (y[i] - m) ** 2 for i in range(len(y)))
    df = len(y) - 1
    C = sw - sum(e * e for e in w) / sw
    return max(0.0, (Q - df) / C) if (df > 0 and C > 0) else 0.0


def tau2_pm(y, v):
    df = len(y) - 1
    if df < 1:
        return 0.0
    if _genQ(y, v, 0) <= df:
        return 0.0
    lo, hi = 0.0, 1.0
    i = 0
    while i < 80 and _genQ(y, v, hi) > df:
        hi *= 2
        i += 1
    for _ in range(100):
        mid = (lo + hi) / 2
        if _genQ(y, v, mid) > df:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def tau2_reml(y, v):
    k = len(y)
    if k < 2:
        return 0.0
    t2 = tau2_dl(y, v)
    for _ in range(300):
        w, sw, m = _wmean(y, v, t2)
        sw2 = sum(e * e for e in w)
        nt = sum(w[i] ** 2 * ((y[i] - m) ** 2 - v[i]) for i in range(k)) / sw2 + 1.0 / sw
        if nt < 0:
            nt = 0.0
        if abs(nt - t2) < 1e-11:
            t2 = nt
            break
        t2 = nt
    return t2


def _tau2(y, v, method: str) -> float:
    if method == "DL":
        return tau2_dl(y, v)
    if method == "REML":
        return tau2_reml(y, v)
    return tau2_pm(y, v)


def pool(items, method: str = "PM", hksj: bool = False) -> dict | None:
    """Pool a list of {hr,lci,uci,inc} dicts (ratio scale). Returns the same
    fields the JS engine exposes. ``items`` use natural-scale point estimate +
    CI (hr/lci/uci naming is historical; works for OR/RR too)."""
    use = [t for t in items if t.get("inc", True) and _valid(t)]
    k = len(use)
    if k < 1:
        return None
    y = [math.log(t["hr"]) for t in use]
    v = [((math.log(t["uci"]) - math.log(t["lci"])) / (2 * Z)) ** 2 for t in use]
    df = k - 1
    tau2 = _tau2(y, v, method)
    wr, swr, re = _wmean(y, v, tau2)
    seRE = math.sqrt(1.0 / swr)
    fxw, fxsw, fxm = _wmean(y, v, 0)
    Q = sum(fxw[i] * (y[i] - fxm) ** 2 for i in range(k))
    if k > 1 and Q > df:
        I2 = max(0.0, (Q - df) / Q) * 100
    elif k > 1:
        I2 = 0.0
    else:
        I2 = None

    if hksj and k >= 2:
        qg = sum(wr[i] * (y[i] - re) ** 2 for i in range(k))
        mult = max(1.0, qg / df)
        ci_half = tcrit(df) * math.sqrt(mult / swr)
        ci_note = "HKSJ"
    else:
        ci_half = Z * seRE
        ci_note = "z"

    pi_lo = pi_hi = None
    if k >= 2:
        h = tcrit(df) * math.sqrt(tau2 + seRE * seRE)
        pi_lo = math.exp(re - h)
        pi_hi = math.exp(re + h)

    return {
        "est": math.exp(re), "ci_lower": math.exp(re - ci_half), "ci_upper": math.exp(re + ci_half),
        "i2": I2, "tau2": tau2, "k": k, "df": df, "Q": Q,
        "pi_lower": pi_lo, "pi_upper": pi_hi,
        "re_log": re, "se_re": seRE, "ci_note": ci_note, "method": method, "hksj": hksj,
    }


def _valid(t) -> bool:
    try:
        hr, lci, uci = t.get("hr"), t.get("lci"), t.get("uci")
        return (hr and lci and uci and hr > 0 and lci > 0 and uci > 0
                and lci <= hr <= uci)
    except (TypeError, ValueError):
        return False


def _normcdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def egger(items):
    """Egger's regression test for funnel-plot asymmetry (radial version per
    advanced-stats.md): OLS of the standard normal deviate z=yi/sei on precision
    x=1/sei; the intercept tests small-study/publication bias. Needs k>=3."""
    use = [t for t in items if t.get("inc", True) and _valid(t)]
    k = len(use)
    if k < 3:
        return None
    y = [math.log(t["hr"]) for t in use]
    v = [((math.log(t["uci"]) - math.log(t["lci"])) / (2 * Z)) ** 2 for t in use]
    z = [y[i] / math.sqrt(v[i]) for i in range(k)]
    x = [1.0 / math.sqrt(v[i]) for i in range(k)]
    n = k
    sx, sz = sum(x), sum(z)
    sxx = sum(xi * xi for xi in x)
    sxz = sum(x[i] * z[i] for i in range(k))
    d = n * sxx - sx * sx
    if d == 0:
        return None
    b = (n * sxz - sx * sz) / d          # slope
    a = (sz - b * sx) / n                # intercept = bias estimate
    s2 = sum((z[i] - (a + b * x[i])) ** 2 for i in range(k)) / (n - 2)
    se = math.sqrt(s2 * sxx / d)
    t = a / se if se > 0 else 0.0
    p = 2.0 * (1.0 - _normcdf(abs(t)))   # normal approx (matches the JS engine)
    return {"intercept": a, "se": se, "t": t, "df": n - 2, "p": p, "k": k}


def leave_one_out(items, method="PM"):
    """Re-pool omitting each included study in turn. Returns a list ordered as
    the input's included studies. Needs k>=3 to be meaningful."""
    use = [t for t in items if t.get("inc", True) and _valid(t)]
    k = len(use)
    if k < 3:
        return []
    out = []
    for i, t in enumerate(use):
        sub = [u for j, u in enumerate(use) if j != i]
        r = pool(sub, method=method)
        out.append({"omitted": t.get("nct") or t.get("name", f"study {i+1}"),
                    "name": t.get("name", ""),
                    "est": r["est"], "lo": r["ci_lower"], "hi": r["ci_upper"]})
    return out


def diagnostics(items, method="PM"):
    """Publication-bias (Egger) + leave-one-out sensitivity for a pairwise set."""
    return {"egger": egger(items), "loo": leave_one_out(items, method=method)}


__all__ = ["pool", "tcrit", "tau2_dl", "tau2_pm", "tau2_reml", "Z", "T975",
           "egger", "leave_one_out", "diagnostics"]
