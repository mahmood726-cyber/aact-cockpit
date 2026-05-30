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
}
cat(sprintf("\n%d pairwise capsules cross-validated with metafor, %d failures\n", checked, fail))
quit(status = if (fail > 0L) 1L else 0L)
