# Run explicitly with --vanilla; no project-wide .Rprofile or global installs.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 1L) stop("Usage: Rscript --vanilla r/restore.R LIBRARY")
script <- sub("^--file=", "", grep("^--file=", commandArgs(), value = TRUE)[[1L]])
project <- dirname(normalizePath(script, winslash = "/", mustWork = TRUE))
required_r <- trimws(readLines(file.path(project, ".R-version"), warn = FALSE))
if (!identical(as.character(getRversion()), required_r)) stop("Install R ", required_r, " before restoring")
library <- args[[1L]]
dir.create(library, recursive = TRUE, showWarnings = FALSE)
library <- normalizePath(library, winslash = "/", mustWork = TRUE)
.libPaths(c(library, .Library), include.site = FALSE)
options(repos = c(CRAN = "https://cloud.r-project.org"), timeout = 300)

# Only the package manager needs bootstrapping. renv restores the actual graph.
# renv is pure R, so this pinned source install does not require a compiler.
renv_version <- "1.3.1"
renv_path <- file.path(library, "renv", "DESCRIPTION")
present <- if (file.exists(renv_path)) read.dcf(renv_path)[1L, "Version"] else ""
if (!identical(unname(present), renv_version)) {
  archive <- paste0("renv_", renv_version, ".tar.gz")
  bundle <- tempfile(fileext = ".tar.gz")
  urls <- paste0("https://cloud.r-project.org/src/contrib/", c("", "Archive/renv/"), archive)
  downloaded <- FALSE
  for (url in urls) {
    result <- tryCatch(utils::download.file(url, bundle, mode = "wb", quiet = TRUE), error = function(e) 1L)
    if (identical(result, 0L)) { downloaded <- TRUE; break }
  }
  if (!downloaded) stop("Could not download pinned renv ", renv_version)
  utils::install.packages(bundle, lib = library, repos = NULL, type = "source")
  unlink(bundle)
}
stopifnot(as.character(packageVersion("renv", lib.loc = library)) == renv_version)
lockfile <- file.path(project, "renv.lock")
lock <- renv::lockfile_read(lockfile)
stopifnot(lock$R$Version == required_r, lock$Packages$renv$Version == renv_version)
# No automatic upgrade fallback and no deletion of unrelated library contents.
renv::restore(project = project, library = library, lockfile = lockfile,
              prompt = FALSE, retry = FALSE, clean = FALSE)
source(file.path(project, "environment.R"))
verify_receiving_environment(lockfile, library)
stopifnot(requireNamespace("nflfastR", quietly = TRUE), requireNamespace("digest", quietly = TRUE))
verify_receiving_environment(lockfile, library)
cat("Receiving R library ready:", library, "\n")
