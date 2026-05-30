"""Contrast-based random-effects network meta-analysis (2-arm trials).

Generalized least squares with a generalized DerSimonian-Laird tau^2 (common
across contrasts), plus a league table and SUCRA from a seeded multivariate
draw. Cross-validated against R netmeta (scripts/r_validate_nma.R).

Effects are on the log scale; a contrast y = log(HR) for treat1 vs treat2
(experimental vs comparator). Lower log-effect = "better" for a harm outcome
like stroke, so SUCRA ranks ascending effect as rank 1.
"""
from __future__ import annotations

import math

import numpy as np

Z = 1.959963984540054


def _seeded_normals(n, seed=2463534242):
    """Deterministic standard normals via xorshift32 + Box-Muller. The xorshift
    is 32-bit so it reproduces BIT-IDENTICALLY in JS (see the capsule template),
    making SUCRA match exactly between Python and the in-browser engine."""
    out = []
    s = seed & 0xFFFFFFFF
    def u():
        nonlocal s
        s ^= (s << 13) & 0xFFFFFFFF
        s ^= (s >> 17)
        s ^= (s << 5) & 0xFFFFFFFF
        s &= 0xFFFFFFFF
        return (s + 0.5) / 4294967296.0
    while len(out) < n:
        u1, u2 = u(), u()
        r = math.sqrt(-2.0 * math.log(max(u1, 1e-12)))
        out.append(r * math.cos(2 * math.pi * u2))
        out.append(r * math.sin(2 * math.pi * u2))
    return out[:n]


def nma(contrasts: list[dict], reference: str | None = None,
        method: str = "DL", n_sim: int = 4000, lower_is_better: bool = True) -> dict:
    """contrasts: [{t1, t2, yi, sei}] (yi = log effect t1 vs t2). Returns the
    network estimates, league table, tau^2/Q, and SUCRA."""
    treatments = sorted({c["t1"] for c in contrasts} | {c["t2"] for c in contrasts})
    if reference is None:
        # most-connected node as reference
        deg: dict[str, int] = {t: 0 for t in treatments}
        for c in contrasts:
            deg[c["t1"]] += 1
            deg[c["t2"]] += 1
        reference = max(treatments, key=lambda t: deg[t])
    others = [t for t in treatments if t != reference]
    idx = {t: i for i, t in enumerate(others)}  # basic-parameter index
    m = len(others)
    n = len(contrasts)
    if n < 1 or m < 1:
        raise ValueError("empty network")

    X = np.zeros((n, m))
    y = np.zeros(n)
    v = np.zeros(n)
    for i, c in enumerate(contrasts):
        y[i] = c["yi"]
        v[i] = c["sei"] ** 2
        if c["t1"] != reference:
            X[i, idx[c["t1"]]] += 1.0
        if c["t2"] != reference:
            X[i, idx[c["t2"]]] -= 1.0

    # fixed-effect fit
    W = np.diag(1.0 / v)
    XtWX = X.T @ W @ X
    XtWX_inv = np.linalg.inv(XtWX)
    theta_fe = XtWX_inv @ X.T @ W @ y
    resid = y - X @ theta_fe
    Q = float(resid.T @ W @ resid)
    df = n - m

    # generalized DL tau^2 (method of moments): tau2 = (Q-df)/C,
    # C = tr(W) - tr( (X'WX)^-1 X'W^2 X )
    if method == "DL" and df > 0 and Q > df:
        W2 = np.diag(1.0 / (v ** 2))
        C = float(np.trace(W) - np.trace(XtWX_inv @ (X.T @ W2 @ X)))
        tau2 = max(0.0, (Q - df) / C) if C > 0 else 0.0
    else:
        tau2 = 0.0

    # random-effects fit
    Wr = np.diag(1.0 / (v + tau2))
    XtWrX = X.T @ Wr @ X
    cov = np.linalg.inv(XtWrX)          # covariance of basic params (vs reference)
    theta = cov @ X.T @ Wr @ y          # log-effects of each 'other' vs reference

    # full treatment vector incl reference (=0) and its covariance (ref row/col 0)
    eff = {reference: 0.0}
    for t in others:
        eff[t] = float(theta[idx[t]])
    full_cov = np.zeros((len(treatments), len(treatments)))
    tindex = {t: i for i, t in enumerate(treatments)}
    for a in others:
        for b in others:
            full_cov[tindex[a], tindex[b]] = cov[idx[a], idx[b]]

    # league table: every ordered pair effect (row vs col) on natural scale
    league = {}
    for a in treatments:
        for b in treatments:
            if a == b:
                continue
            d = eff[a] - eff[b]
            var = (full_cov[tindex[a], tindex[a]] + full_cov[tindex[b], tindex[b]]
                   - 2 * full_cov[tindex[a], tindex[b]])
            se = math.sqrt(max(var, 0.0))
            league[f"{a}|{b}"] = {"est": math.exp(d), "lo": math.exp(d - Z * se),
                                  "hi": math.exp(d + Z * se), "log": d, "se": se}

    sucra = _sucra(treatments, eff, full_cov, n_sim=n_sim, lower_is_better=lower_is_better)

    return {
        "treatments": treatments, "reference": reference,
        "effects": eff,                      # log-scale vs reference
        "rel_to_ref": {t: {"est": math.exp(eff[t]),
                           "lo": math.exp(eff[t] - Z * math.sqrt(full_cov[tindex[t], tindex[t]])),
                           "hi": math.exp(eff[t] + Z * math.sqrt(full_cov[tindex[t], tindex[t]]))}
                       for t in treatments},
        "league": league, "tau2": tau2, "Q": Q, "df": df, "k": n,
        "sucra": sucra, "method": method,
        "edges": _edges(contrasts),
    }


def _sucra(treatments, eff, cov, n_sim=4000, lower_is_better=True):
    m = len(treatments)
    L = np.linalg.cholesky(cov + np.eye(m) * 1e-12)
    mu = np.array([eff[t] for t in treatments])
    rank_count = np.zeros((m, m))  # rank_count[t, r] how often treat t got rank r
    normals = _seeded_normals(n_sim * m)
    for s in range(n_sim):
        zvec = np.array(normals[s * m:(s + 1) * m])
        draw = mu + L @ zvec
        order = np.argsort(draw if lower_is_better else -draw)  # rank 1 = best
        for rank, ti in enumerate(order):
            rank_count[ti, rank] += 1
    rank_prob = rank_count / n_sim
    sucra = {}
    for i, t in enumerate(treatments):
        cum = 0.0
        for r in range(m - 1):
            cum += rank_prob[i, :r + 1].sum()
        sucra[t] = cum / (m - 1) if m > 1 else 1.0
    return sucra


def _edges(contrasts):
    e = {}
    for c in contrasts:
        key = "|".join(sorted([c["t1"], c["t2"]]))
        e[key] = e.get(key, 0) + 1
    return [{"a": k.split("|")[0], "b": k.split("|")[1], "n": v} for k, v in e.items()]


def connectivity(treatments, edges) -> bool:
    """BFS — are all treatments reachable (connected network)?"""
    if not treatments:
        return False
    adj = {t: set() for t in treatments}
    for e in edges:
        adj[e["a"]].add(e["b"])
        adj[e["b"]].add(e["a"])
    seen = {treatments[0]}
    stack = [treatments[0]]
    while stack:
        node = stack.pop()
        for nb in adj[node]:
            if nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return len(seen) == len(treatments)


def has_loops(treatments, edges) -> bool:
    """A connected graph has a cycle iff |edges| >= |nodes| (distinct edges)."""
    distinct = {tuple(sorted([e["a"], e["b"]])) for e in edges}
    return len(distinct) >= len(treatments)


__all__ = ["nma", "connectivity", "has_loops"]
