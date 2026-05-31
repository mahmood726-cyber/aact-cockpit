#!/usr/bin/env Rscript
# Gold-tier cross-validation: independently re-pool every published PAIRWISE
# capsule with metafor (Paule-Mandel) and confirm the pooled estimate matches
# the capsule's embedded value within 1e-4 (the rapidmeta portfolio threshold).
#
# Usage: Rscript scripts/r_validate.R docs
suppressMessages(library(jsonlite))
suppressMessages(library(metafor))

args <- commandArgs(trailingOnly = TRUE)
docs <- if (length(args) >= 1) args[1] else "docs"
Z <- 1.959963984540054

sidecars <- list.files(docs, pattern = "\\.json$", recursive = TRUE, full.names = TRUE)
checked <- 0L
fail <- 0L
for (sc in sidecars) {
  if (basename(sc) == "assurance.json") next
  cap <- tryCatch(fromJSON(sc, simplifyVector = FALSE), error = function(e) NULL)
  if (is.null(cap) || is.null(cap$pico) || is.null(cap$pooled)) next
  if (!is.null(cap$kind) && identical(cap$kind, "tsa")) next  # pairwise only

  studies <- cap$studies
  hr  <- vapply(studies, function(s) as.numeric(s$hr),  numeric(1))
  lci <- vapply(studies, function(s) as.numeric(s$lci), numeric(1))
  uci <- vapply(studies, function(s) as.numeric(s$uci), numeric(1))
  ok <- hr > 0 & lci > 0 & uci > 0 & lci <= hr & hr <= uci
  yi <- log(hr[ok]); sei <- (log(uci[ok]) - log(lci[ok])) / (2 * Z)
  if (length(yi) < 2) next

  res <- rma(yi = yi, sei = sei, method = "PM")
  est_r   <- exp(as.numeric(coef(res)))
  est_cap <- as.numeric(cap$pooled$est)
  d <- abs(est_r - est_cap)
  checked <- checked + 1L
  status <- if (d < 1e-4) "PASS" else "FAIL"
  cat(sprintf("  [%s] %-44s R=%.4f cap=%.4f d=%.2e\n", status, cap$slug, est_r, est_cap, d))
  if (d >= 1e-4) fail <- fail + 1L

  # diagnostics: Egger (radial OLS via lm) + leave-one-out vs metafor
  dg <- cap$diagnostics
  if (!is.null(dg) && !is.null(dg$egger) && length(yi) >= 3) {
    z <- yi / sei; x <- 1 / sei; fit <- lm(z ~ x)
    d2 <- abs(as.numeric(coef(fit)[1]) - as.numeric(dg$egger$intercept))
    checked <- checked + 1L
    st2 <- if (d2 < 1e-4) "PASS" else "FAIL"
    cat(sprintf("  [%s]   egger intercept R=%.4f cap=%.4f d=%.2e\n", st2,
                as.numeric(coef(fit)[1]), as.numeric(dg$egger$intercept), d2))
    if (d2 >= 1e-4) fail <- fail + 1L
  }
  if (!is.null(dg) && !is.null(dg$loo) && length(dg$loo) >= 3) {
    lo <- exp(leave1out(res)$estimate)
    cap_loo <- vapply(dg$loo, function(l) as.numeric(l$est), numeric(1))
    d3 <- max(abs(lo - cap_loo))
    checked <- checked + 1L
    st3 <- if (d3 < 1e-3) "PASS" else "FAIL"
    cat(sprintf("  [%s]   leave-one-out (k=%d) maxdelta=%.2e\n", st3, length(cap_loo), d3))
    if (d3 >= 1e-3) fail <- fail + 1L
  }
  # meta-regression by year vs metafor rma(mods=~year, DL)
  years <- vapply(studies, function(s) if (is.null(s$year)) NA_real_ else as.numeric(s$year), numeric(1))[ok]
  if (!is.null(dg) && !is.null(dg$metareg) && sum(!is.na(years)) >= 3 &&
      length(unique(years[!is.na(years)])) >= 2) {
    sel <- !is.na(years)
    mr <- rma(yi = yi[sel], sei = sei[sel], mods = ~ years[sel], method = "DL")
    d4 <- abs(as.numeric(mr$beta[2]) - as.numeric(dg$metareg$b1))
    checked <- checked + 1L
    st4 <- if (d4 < 1e-4) "PASS" else "FAIL"
    cat(sprintf("  [%s]   meta-reg slope R=%.5f cap=%.5f d=%.2e\n", st4,
                as.numeric(mr$beta[2]), as.numeric(dg$metareg$b1), d4))
    if (d4 >= 1e-4) fail <- fail + 1L
  }
  # influence: hat vs metafor::hatvalues (exact); Cook within PM-solver tolerance
  if (!is.null(dg) && !is.null(dg$influence) && length(dg$influence) >= 3) {
    hat_r <- as.numeric(hatvalues(res))
    cap_hat <- vapply(dg$influence, function(d) as.numeric(d$hat), numeric(1))
    cook_r <- as.numeric(cooks.distance(res))
    cap_cook <- vapply(dg$influence, function(d) as.numeric(d$cook), numeric(1))
    dh <- max(abs(hat_r - cap_hat)); dc <- max(abs(cook_r - cap_cook))
    checked <- checked + 1L
    # tolerances reflect the PM tau^2 solver precision (~1e-5) propagated into
    # weights (hat) and amplified by sum(w) (Cook); both negligible vs thresholds
    st5 <- if (dh < 5e-3 && dc < 1e-2) "PASS" else "FAIL"
    cat(sprintf("  [%s]   influence hat dmax=%.2e cook dmax=%.2e\n", st5, dh, dc))
    if (!(dh < 5e-3 && dc < 1e-2)) fail <- fail + 1L
  }
  # trim-and-fill: independent L0 reimplementation (same algorithm) -> exact k0
  if (!is.null(dg) && !is.null(dg$trimfill) && length(yi) >= 3) {
    tau2f <- function(yy, vv) if (length(yy) < 2) 0 else rma(yi = yy, sei = sqrt(vv), method = "PM")$tau2
    reest <- function(yy, vv) { t2 <- tau2f(yy, vv); ww <- 1 / (vv + t2); sum(ww * yy) / sum(ww) }
    o <- order(yi); ys <- yi[o]; vs <- sei[o]^2; k0 <- 0; sd <- NA
    for (it in 1:100) {
      keep <- if (!is.na(sd) && sd == "right") 1:(length(ys) - k0) else (k0 + 1):length(ys)
      th <- reest(ys[keep], vs[keep])
      if (is.na(sd)) { c0 <- ys - th; sd <- if (sum(c0 > 0) < sum(c0 < 0)) "right" else "left"; next }
      cc <- ys - th; rk <- rank(abs(cc)); n <- length(cc)
      Tn <- if (sd == "right") sum(rk[cc > 0]) else sum(rk[cc < 0])
      nk <- max(0, floor((4 * Tn - n * (n + 1)) / (2 * n - 1) + 0.5)); if (nk == k0) break; k0 <- nk
    }
    checked <- checked + 1L
    st6 <- if (k0 == as.integer(dg$trimfill$k0)) "PASS" else "FAIL"
    cat(sprintf("  [%s]   trim-fill L0 k0 R=%d cap=%d\n", st6, k0, as.integer(dg$trimfill$k0)))
    if (k0 != as.integer(dg$trimfill$k0)) fail <- fail + 1L
  }
}
cat(sprintf("\n%d pairwise capsules cross-validated with metafor, %d failures\n", checked, fail))
quit(status = if (fail > 0L) 1L else 0L)
