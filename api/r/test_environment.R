# Network-free checks of the dependency gate, after restore.R has succeeded.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) stop("Usage: Rscript --vanilla r/test_environment.R LIBRARY")
script <- sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE)[[1L]])
project <- dirname(normalizePath(script, winslash = "/", mustWork = TRUE))
source(file.path(project, "environment.R"))
lockfile <- file.path(project, "renv.lock")
library <- normalizePath(args[[1L]], winslash = "/", mustWork = TRUE)
lock <- verify_receiving_environment(lockfile, library)
stopifnot(requireNamespace("nflfastR", quietly = TRUE))
verify_receiving_environment(lockfile, library)
expect_error <- function(fn, pattern) {
  error <- tryCatch({ fn(); NULL }, error = identity)
  stopifnot(inherits(error, "error"), grepl(pattern, conditionMessage(error), fixed = TRUE))
}
changed <- tempfile(fileext = ".lock")
wrong_r <- lock
wrong_r$R$Version <- "0.0.0"
jsonlite::write_json(wrong_r, changed, auto_unbox = TRUE)
expect_error(function() verify_receiving_environment(changed, library), "Expected R")
wrong_package <- lock
wrong_package$Packages$dplyr$Version <- "0.0.0"
jsonlite::write_json(wrong_package, changed, auto_unbox = TRUE)
expect_error(function() verify_receiving_environment(changed, library), "dplyr")
incomplete <- lock
incomplete$Packages$curl <- NULL
jsonlite::write_json(incomplete, changed, auto_unbox = TRUE)
expect_error(function() verify_receiving_environment(changed, library), "dependencies absent from renv.lock")
# Even if packages were loaded earlier or exposed via user/site configuration,
# an empty target library cannot borrow the experiment's installed packages.
empty <- tempfile()
dir.create(empty)
expect_error(function() verify_receiving_environment(lockfile, empty), "packages differ from renv.lock")
verify_receiving_environment(lockfile, library)
unlink(changed)
unlink(empty, recursive = FALSE)
cat("PASS: matching environment, wrong R, transitive version drift, incomplete lock, isolated library\n")
