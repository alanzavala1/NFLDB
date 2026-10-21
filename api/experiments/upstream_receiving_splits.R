# Official receiving export producer; never imports or writes a database.
# Rscript --vanilla experiments/upstream_receiving_splits.R OUTPUT_DIR [SEASONS...]
# R_LIBS_USER may point at a separate experiment-only package library.
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1L) stop("Supply an experiment output directory")
out <- args[[1L]]
years <- if (length(args) > 1L) as.integer(args[-1L]) else c(2024L, 2004L)
stopifnot(!anyNA(years), all(years >= 1999L), !anyDuplicated(years))
dir.create(out, recursive = TRUE, showWarnings = FALSE)
out <- normalizePath(out, winslash = "/", mustWork = TRUE)
# A failed rerun must not leave a previous completion marker behind.
completion <- file.path(out, "run.json")
if (file.exists(completion)) file.remove(completion)
options(timeout = 300, nflreadr.cache = "memory")
stopifnot(requireNamespace("jsonlite", quietly = TRUE))
stopifnot(as.character(packageVersion("nflfastR")) == "6.0.0")
stopifnot(as.character(packageVersion("nflreadr")) == "1.5.1")
stopifnot("pbp" %in% names(formals(nflfastR::calculate_stats)))
metrics <- c("targets", "receptions", "receiving_yards", "receiving_tds",
             "receiving_yards_after_catch", "receiving_first_downs", "receiving_epa",
             "receiving_air_yards")
selected <- c("player_id", "season", "season_type", metrics)
timings <- list()
record <- function(label, fn) {
  cat(format(Sys.time(), tz = "UTC"), label, "START\n")
  flush.console()
  elapsed <- system.time(value <- fn())[["elapsed"]]
  timings[[length(timings) + 1L]] <<- data.frame(step = label, seconds = elapsed)
  cat(label, "DONE", elapsed, "seconds\n")
  flush.console()
  value
}
write_frame <- function(frame, name) {
  write.csv(as.data.frame(frame), file.path(out, name), row.names = FALSE, na = "")
}
calculate <- function(plays) {
  # Filter play context, not original-receiver identity. The official function
  # finds all credited players on those plays, including lateral recipients.
  nflfastR::calculate_stats(
    summary_level = "season", stat_type = "player", season_type = "REG", pbp = plays
  )
}
input_records <- list()
for (year in years) {
  pbp <- record(paste(year, "load_pbp"), function() nflreadr::load_pbp(year))
  weekly <- record(paste(year, "load_weekly"), function() {
    nflreadr::load_player_stats(year, summary_level = "week")
  })
  saveRDS(pbp, file.path(out, paste0("pbp-", year, ".rds")))
  saveRDS(weekly, file.path(out, paste0("weekly-", year, ".rds")))
  reg <- pbp[pbp$season_type %in% "REG" & !(pbp$two_point_attempt %in% 1), ]
  stopifnot(!anyDuplicated(reg[c("game_id", "play_id")]))
  write_frame(reg[c("game_id", "play_id", "season", "season_type", "down", "qtr",
                    "two_point_attempt", "receiver_player_id", "complete_pass",
                    "incomplete_pass", "interception", "epa", "air_yards",
                    "receiving_yards", "pass_touchdown")], paste0("context-", year, ".csv"))
  write_frame(weekly[weekly$season_type %in% "REG", c("player_id", "season", "season_type", "week", metrics)],
              paste0("weekly-", year, ".csv"))
  full <- record(paste(year, "full_calculation"), function() calculate(reg))
  stopifnot(isTRUE(attr(full, "custom_pbp")))
  write_frame(full[selected], paste0("overall-", year, ".csv"))
  # A second identical run gives a warm-cache measurement, not a benchmark of
  # production throughput. All bucket calculations are sequential in this trial.
  if (year == 2024L) {
    repeat_full <- record(paste(year, "warm_full_calculation"), function() calculate(reg))
    stopifnot(isTRUE(all.equal(as.data.frame(full), as.data.frame(repeat_full))))
  }
  dimensions <- list(down = as.character(1:4), quarter = c(as.character(1:4), "OT"))
  for (dimension in names(dimensions)) {
    buckets <- lapply(dimensions[[dimension]], function(bucket) {
      period <- if (dimension == "down") reg$down else reg$qtr
      keep <- if (bucket == "OT") !is.na(period) & period > 4 else period %in% as.integer(bucket)
      plays <- reg[keep, ]
      # No invented zero rows when a season has no plays in a bucket.
      if (nrow(plays) == 0L) return(NULL)
      stats <- record(paste(year, dimension, bucket), function() calculate(plays))
      stopifnot(isTRUE(attr(stats, "custom_pbp")))
      frame <- as.data.frame(stats[selected])
      frame$split_value <- bucket
      frame
    })
    write_frame(do.call(rbind, buckets), paste0(dimension, "-", year, ".csv"))
  }
  # Capture the raw records used by the upstream credit loader for a separate
  # comparison with our existing isolated Python prototype. Do not deduplicate.
  credits <- nflfastR:::load_playstats(year)
  saveRDS(credits, file.path(out, paste0("credits-", year, ".rds")))
  write_frame(as.data.frame(credits)[c("game_id", "play_id", "gsis_player_id", "stat_id", "yards")],
              paste0("credits-", year, ".csv"))
  input_records[[as.character(year)]] <- list(
    all_plays = nrow(pbp), regular_nonconversion_plays = nrow(reg),
    missing_down_plays = sum(!(reg$down %in% 1:4)),
    missing_quarter_plays = sum(is.na(reg$qtr)),
    weekly_rows = nrow(weekly), raw_credit_rows = nrow(credits)
  )
}
write_frame(do.call(rbind, timings), "timings.csv")
capture.output(sessionInfo(), file = file.path(out, "session-info.txt"))
capture.output(nflfastR::calculate_stats, file = file.path(out, "installed-calculator.txt"))
# Bind the consumed exports and captured source inputs before writing completion.
files <- unlist(lapply(years, function(year) c(
  paste0(c("context-", "weekly-", "overall-", "down-", "quarter-", "credits-"), year, ".csv"),
  paste0(c("pbp-", "weekly-", "credits-"), year, ".rds")
)))
hashes <- setNames(lapply(files, function(name) {
  digest::digest(file = file.path(out, name), algo = "sha256", serialize = FALSE)
}), files)
packages <- setNames(lapply(loadedNamespaces(), function(name) {
  as.character(packageVersion(name))
}), loadedNamespaces())
jsonlite::write_json(list(
  seasons = as.list(years), nflfastR = as.character(packageVersion("nflfastR")),
  nflreadr = as.character(packageVersion("nflreadr")),
  receiving_export = list(
    schema_version = 6L, season_type = "REG", excludes_two_point_attempts = TRUE,
    summary_level = "season", split_dimensions = c("down", "quarter")
  ),
  run_id = Sys.getenv("NFL_RECEIVING_RUN_ID", unset = NA_character_),
  runtime = list(R = as.character(getRversion()), platform = R.version$platform,
                 packages = packages),
  files = hashes,
  scope = "REG, excluding two-point attempts; identified-player comparisons done separately",
  inputs = input_records, completed_utc = format(Sys.time(), tz = "UTC", usetz = TRUE)
), completion, pretty = TRUE, auto_unbox = TRUE)
cat("TRIAL COMPLETE\n")
