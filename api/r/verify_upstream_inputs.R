# Compare decoded published inputs with the tables consumed by the frozen producer.
# No network, namespace replacement, calculation or database access.
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 2L)
out <- normalizePath(args[[1L]], winslash = "/", mustWork = TRUE)
source(file.path(out, "environment.R"))
verify_receiving_environment(file.path(out, "renv.lock"), args[[2L]])
request <- jsonlite::read_json(file.path(out, "upstream-request.json"), simplifyVector = FALSE)
results <- list()
for (key in names(request$assets)) {
  item <- request$assets[[key]]
  stopifnot(basename(item$download_file) == item$download_file,
            basename(item$consumed_file) == item$consumed_file)
  downloaded <- file.path(out, item$download_file)
  consumed <- file.path(out, item$consumed_file)
  stopifnot(digest::digest(file = downloaded, algo = "sha256", serialize = FALSE) == item$download_sha256,
            digest::digest(file = consumed, algo = "sha256", serialize = FALSE) == item$consumed_sha256)
  expected <- as.data.frame(readRDS(downloaded))
  actual <- as.data.frame(readRDS(consumed))
  stopifnot("season" %in% names(expected), "season" %in% names(actual))
  expected <- expected[expected$season %in% request$season, , drop = FALSE]
  stopifnot(nrow(expected) > 0L, nrow(actual) == nrow(expected),
            identical(names(actual), names(expected)),
            all(actual$season %in% request$season))
  # Compare every typed column exactly. Ignore only frame-level wrappers such as
  # nflverse download timestamps and data.table's self-reference pointer.
  if (!all(vapply(seq_along(expected), function(i) identical(actual[[i]], expected[[i]]), logical(1)))) {
    stop("Consumed values differ from published asset: ", key)
  }
  results[[key]] <- list(status = "equal", rows = nrow(actual),
                        download_sha256 = item$download_sha256, consumed_sha256 = item$consumed_sha256)
}
jsonlite::write_json(results, file.path(out, "upstream-result.json"), auto_unbox = TRUE, pretty = TRUE)
