#!/usr/bin/env Rscript
# Cross-validate every published NMA capsule against R netmeta: read the capsule
# sidecar (which embeds the contrasts + the Python NMA result), re-fit with
# netmeta, and confirm each treatment's random-effects HR vs the reference
# matches within tolerance. Self-contained — reads only committed docs/.
#
# Usage: Rscript scripts/r_validate_nma.R docs
suppressMessages(library(jsonlite))
suppressMessages(library(netmeta))

args <- commandArgs(trailingOnly = TRUE)
docs <- if (length(args) >= 1) args[1] else "docs"

sidecars <- list.files(docs, pattern = "\\.json$", recursive = TRUE, full.names = TRUE)
checked <- 0L; fail <- 0L; nfiles <- 0L
for (sc in sidecars) {
  if (basename(sc) == "assurance.json") next
  cap <- tryCatch(fromJSON(sc, simplifyVector = FALSE), error = function(e) NULL)
  if (is.null(cap) || is.null(cap$kind) || !identical(cap$kind, "nma")) next
  nfiles <- nfiles + 1L
  ct <- cap$contrasts
  ref <- cap$nma$reference
  TE   <- vapply(ct, function(c) as.numeric(c$yi),  numeric(1))
  seTE <- vapply(ct, function(c) as.numeric(c$sei), numeric(1))
  t1   <- vapply(ct, function(c) as.character(c$t1), character(1))
  t2   <- vapply(ct, function(c) as.character(c$t2), character(1))
  sl   <- vapply(ct, function(c) as.character(c$nct), character(1))

  net <- netmeta(TE = TE, seTE = seTE, treat1 = t1, treat2 = t2, studlab = sl,
                 sm = "HR", reference.group = ref, common = FALSE, random = TRUE,
                 method.tau = "DL")
  hr_r <- exp(net$TE.random[, ref])
  cat(sprintf("%s  (netmeta tau^2=%.4f, python tau^2=%.4f)\n", basename(sc),
              net$tau^2, as.numeric(cap$nma$tau2)))
  for (t in names(hr_r)) {
    if (t == ref) next
    est_r  <- as.numeric(hr_r[[t]])
    est_py <- as.numeric(cap$nma$rel_to_ref[[t]]$est)
    d <- abs(est_r - est_py)
    checked <- checked + 1L
    status <- if (d < 0.01) "PASS" else "FAIL"
    cat(sprintf("  [%s] %-12s netmeta HR=%.4f  python HR=%.4f  d=%.2e\n", status, t, est_r, est_py, d))
    if (d >= 0.01) fail <- fail + 1L
  }
}
cat(sprintf("\n%d NMA capsule(s), %d treatment estimates cross-validated vs netmeta, %d failures\n",
            nfiles, checked, fail))
quit(status = if (fail > 0L) 1L else 0L)
