# Official receiving export producer; never imports or writes a database.
# Rscript --vanilla experiments/upstream_receiving_splits.R OUTPUT_DIR [SEASONS...]
# R_LIBS_USER may point at a separate experiment-only package library.
# jobs.receiving_preview prepares definitions.json and bound FTN inputs first.
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
definitions <- jsonlite::read_json(file.path(out, "definitions.json"), simplifyVector = TRUE)
dimensions <- definitions$dimensions
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
  charting <- read.csv(file.path(out, paste0("ftn-", year, ".csv")))
  stopifnot(all(charting$season %in% year), !anyDuplicated(charting[c("game_id", "play_id")]))
  charting$ftn_matched <- rep(1L, nrow(charting))
  reg$.source_order <- seq_len(nrow(reg))
  reg <- merge(as.data.frame(reg), charting, by = c("game_id", "play_id", "season"), all.x = TRUE, sort = FALSE)
  reg <- reg[order(reg$.source_order), ]
  stopifnot(nrow(reg) == sum(pbp$season_type %in% "REG" & !(pbp$two_point_attempt %in% 1)))
  reg$ftn_matched[is.na(reg$ftn_matched)] <- 0L
  write_frame(reg[c("game_id", "play_id", "season", "season_type", "down", "qtr", "shotgun", "yardline_100", "score_differential", "no_huddle",
                    "posteam_type", "posteam", "home_team", "away_team", "location",
                    "wp", "roof", "surface", "defteam", "pass_length", "pass_location", "qb_hit",
                    "is_play_action", "n_pass_rushers", "ftn_matched",
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
  for (dimension in names(dimensions)) {
    # One assignment per play drives the exported membership and every subset.
    # Python independently derives these labels from the bound context export.
    labels <- rep(NA_character_, nrow(reg))
    if (dimension %in% c("opponent", "opp_division")) {
      opponent <- reg$defteam
      for (alias in names(definitions$modern_aliases)) opponent[opponent %in% alias] <- definitions$modern_aliases[[alias]]
      if (dimension == "opp_division") {
        opponent <- unname(unlist(definitions$divisions)[opponent])
      } else {
        for (relocation_index in seq_len(nrow(definitions$relocations))) {
          relocation <- definitions$relocations[relocation_index, ]
          if (year <= as.integer(relocation[[3L]])) opponent[opponent %in% relocation[[1L]]] <- relocation[[2L]]
        }
      }
    }
    for (bucket in dimensions[[dimension]]) {
      keep <- switch(dimension,
        home_away = reg$posteam_type %in% bucket,
        shotgun = reg$shotgun %in% (if (bucket == "shotgun") 1L else 0L),
        no_huddle = reg$no_huddle %in% (if (bucket == "no_huddle") 1L else 0L),
        roof = reg$roof %in% names(definitions$roofs)[unlist(definitions$roofs) == bucket],
        surface = reg$surface %in% names(definitions$surfaces)[unlist(definitions$surfaces) == bucket],
        game_state = !is.na(reg$wp) & (if (bucket == "competitive") reg$wp >= 0.05 & reg$wp <= 0.95 else reg$wp < 0.05 | reg$wp > 0.95),
        opponent = opponent %in% bucket,
        opp_division = opponent %in% bucket,
        target_depth = reg$pass_length %in% bucket,
        target_direction = reg$pass_location %in% bucket,
        pressure = year >= definitions$pressure_first_season & reg$qb_hit %in% (if (bucket == "pressured") 1L else 0L),
        play_action = year >= definitions$ftn_first_season & reg$is_play_action %in% (if (bucket == "play_action") 1L else 0L),
        blitz = year >= definitions$ftn_first_season & !is.na(reg$n_pass_rushers) & (if (bucket == "blitz") reg$n_pass_rushers >= 5 & reg$n_pass_rushers <= 11 else reg$n_pass_rushers >= 1 & reg$n_pass_rushers <= 4),
        game_script = !is.na(reg$score_differential) & switch(bucket,
          leading = reg$score_differential > 0,
          tied = reg$score_differential == 0,
          trailing = reg$score_differential < 0),
        field_zone = !is.na(reg$yardline_100) & switch(bucket,
          own_territory = reg$yardline_100 > 50,
          opp_territory = reg$yardline_100 > 20 & reg$yardline_100 <= 50,
          red_zone = reg$yardline_100 <= 20),
        {
          period <- if (dimension == "down") reg$down else reg$qtr
          if (bucket == "OT") !is.na(period) & period > 4 else period %in% as.integer(bucket)
        }
      )
      stopifnot(!anyNA(keep), all(is.na(labels[keep])))
      labels[keep] <- bucket
    }
    membership <- as.data.frame(reg[c("game_id", "play_id")])
    membership$split_value <- labels
    write_frame(membership, paste0("membership-", dimension, "-", year, ".csv"))
    empty <- as.data.frame(full[0, selected])
    subset_stats <- function(keep, label) {
      if (!any(keep)) return(empty)
      # The full result is already the official reference for this exact set.
      if (all(keep)) return(as.data.frame(full[selected]))
      stats <- record(paste(year, dimension, label), function() calculate(reg[keep, ]))
      stopifnot(isTRUE(attr(stats, "custom_pbp")))
      as.data.frame(stats[selected])
    }
    write_frame(subset_stats(!is.na(labels), "classified"),
                paste0("classified-", dimension, "-", year, ".csv"))
    write_frame(subset_stats(is.na(labels), "excluded"),
                paste0("excluded-", dimension, "-", year, ".csv"))
    buckets <- lapply(dimensions[[dimension]], function(bucket) {
      # No invented zero rows when a season has no plays in a bucket.
      frame <- subset_stats(labels %in% bucket, bucket)
      frame$split_value <- rep(bucket, nrow(frame))
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
    missing_home_away_plays = sum(is.na(reg$posteam_type)),
    missing_shotgun_plays = sum(is.na(reg$shotgun)),
    missing_field_zone_plays = sum(is.na(reg$yardline_100)),
    missing_game_script_plays = sum(is.na(reg$score_differential)),
    missing_no_huddle_plays = sum(is.na(reg$no_huddle)),
    weekly_rows = nrow(weekly), raw_credit_rows = nrow(credits)
  )
}
write_frame(do.call(rbind, timings), "timings.csv")
capture.output(sessionInfo(), file = file.path(out, "session-info.txt"))
capture.output(nflfastR::calculate_stats, file = file.path(out, "installed-calculator.txt"))
# Bind the consumed exports and captured source inputs before writing completion.
files <- c("producer.R", "definitions.json", "ftn-inputs.json", unlist(lapply(years, function(year) c(
  paste0(c("context-", "weekly-", "overall-", paste0(names(dimensions), "-"), "credits-"), year, ".csv"),
  unlist(lapply(c("membership", "classified", "excluded"), function(kind)
    paste0(kind, "-", names(dimensions), "-", year, ".csv"))),
  paste0(c("pbp-", "weekly-", "credits-"), year, ".rds"), paste0("ftn-", year, ".csv")
))))
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
    schema_version = 13L, season_type = "REG", excludes_two_point_attempts = TRUE,
    summary_level = "season", split_dimensions = names(dimensions)
  ),
  run_id = Sys.getenv("NFL_RECEIVING_RUN_ID", unset = NA_character_),
  runtime = list(R = as.character(getRversion()), platform = R.version$platform,
                 packages = packages),
  files = hashes,
  scope = "REG, excluding two-point attempts; identified-player comparisons done separately",
  inputs = input_records, completed_utc = format(Sys.time(), tz = "UTC", usetz = TRUE)
), completion, pretty = TRUE, auto_unbox = TRUE)
cat("TRIAL COMPLETE\n")
