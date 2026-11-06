# Convert captured calculator inputs for Python ingestion. No downloads or DB writes.
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 3L)
root <- normalizePath(args[[1L]], winslash = "/", mustWork = TRUE)
out <- normalizePath(args[[2L]], winslash = "/", mustWork = TRUE)
source(file.path(out, "environment.R"))
verify_receiving_environment(file.path(out, "renv.lock"), args[[3L]])
manifest <- jsonlite::read_json(file.path(out, "receiving-run.json"), simplifyVector = FALSE)
spec <- jsonlite::read_json(file.path(out, "columns.json"), simplifyVector = TRUE)
records <- list()
missing_value <- "__NFLDB_MISSING_VALUE__"
for (year in unlist(manifest$seasons)) {
  for (kind in c("pbp", "weekly")) {
    input <- paste0(kind, "-", year, ".rds")
    path <- file.path(root, input)
    stopifnot(digest::digest(file = path, algo = "sha256", serialize = FALSE) == manifest$files[[input]])
    frame <- as.data.frame(readRDS(path))
    if (kind == "pbp") frame <- frame[intersect(spec$plays, names(frame))]
    types <- vapply(frame, typeof, character(1))
    stopifnot(all(types %in% c("character", "integer", "double", "logical")))
    stopifnot(!any(vapply(frame, is.object, logical(1))))
    stopifnot(!any(vapply(frame, function(column) any(column %in% missing_value), logical(1))))
    name <- paste0(if (kind == "pbp") "plays" else "weekly", "-", year, ".csv")
    write.csv(frame, file.path(out, name), row.names = FALSE, na = missing_value,
              fileEncoding = "UTF-8")
    records[[name]] <- list(rows = nrow(frame), columns = as.list(types), source = input,
                            source_sha256 = manifest$files[[input]])
    # Detect a changed input even if another process edited it while R read it.
    stopifnot(digest::digest(file = path, algo = "sha256", serialize = FALSE) == manifest$files[[input]])
  }
}
verify_receiving_environment(file.path(out, "renv.lock"), args[[3L]])
files <- c("bridge.R", "environment.R", "renv.lock", "receiving-run.json", "columns.json", names(records))
hashes <- setNames(lapply(files, function(name) {
  digest::digest(file = file.path(out, name), algo = "sha256", serialize = FALSE)
}), files)
jsonlite::write_json(list(format_version = 1L, seasons = manifest$seasons,
                         source_directory = root, missing_value = missing_value,
                         files = hashes, tables = records),
                    file.path(out, "run.json"), pretty = TRUE, auto_unbox = TRUE)
cat("Captured core inputs converted; no source refresh or publication performed\n")
