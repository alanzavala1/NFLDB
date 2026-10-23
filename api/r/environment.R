# Shared by setup, preflight, and the frozen export producer. No downloads.
verify_receiving_environment <- function(lockfile, library) {
  if (!nzchar(library) || !dir.exists(library)) stop("Supply an existing R package library")
  library <- normalizePath(library, winslash = "/", mustWork = TRUE)
  # Exclude user/site libraries. R's own base/recommended library is permitted,
  # but every non-base dependency must match the lock, including recommended ones.
  .libPaths(c(library, .Library), include.site = FALSE)
  if (!requireNamespace("jsonlite", quietly = TRUE)) stop("Run r/restore.R before building")
  lock <- jsonlite::read_json(lockfile, simplifyVector = FALSE)
  if (!identical(as.character(getRversion()), lock$R$Version)) {
    stop("Expected R ", lock$R$Version, "; found ", getRversion())
  }
  expected <- vapply(lock$Packages, function(record) record$Version, character(1))
  installed <- installed.packages(lib.loc = .libPaths(), noCache = TRUE)
  actual <- installed[match(names(expected), installed[, "Package"]), "Version"]
  bad <- names(expected)[is.na(actual) | actual != expected]
  if (length(bad)) stop("R packages differ from renv.lock: ", paste(bad, collapse = ", "), "; run r/restore.R")
  # Detect an incomplete lock, including a newly introduced transitive import.
  dependencies <- tools::package_dependencies(names(expected), db = installed,
                                               which = c("Depends", "Imports", "LinkingTo"), recursive = TRUE)
  base <- installed[installed[, "Priority"] %in% "base", "Package"]
  unlocked <- setdiff(unique(c(unlist(dependencies), loadedNamespaces())), c(names(expected), base))
  if (length(unlocked)) stop("R dependencies absent from renv.lock: ", paste(unlocked, collapse = ", "))
  invisible(lock)
}

if (sys.nframe() == 0L) {
  args <- commandArgs(trailingOnly = TRUE)
  if (length(args) != 2L) stop("Usage: Rscript --vanilla environment.R LOCKFILE LIBRARY")
  lock <- verify_receiving_environment(args[[1L]], args[[2L]])
  # Load compiled dependencies too; a matching DESCRIPTION alone is insufficient.
  stopifnot(requireNamespace("nflfastR", quietly = TRUE), requireNamespace("digest", quietly = TRUE))
  verify_receiving_environment(args[[1L]], args[[2L]])
  cat("Receiving R environment verified:", lock$R$Version, ";", length(lock$Packages), "locked packages\n")
}
