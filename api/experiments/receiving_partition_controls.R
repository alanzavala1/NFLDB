# Frozen real-data controls for the pure partition validator, not a new split view.
# Rscript --vanilla experiments/receiving_partition_controls.R EXPORT_ROOT CHART_CSV CHART_SHA OUTPUT_JSON
args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 4L)
root <- args[[1L]]
chart_path <- args[[2L]]
stopifnot(digest::digest(file = chart_path, algo = "sha256", serialize = FALSE) == args[[3L]])
stopifnot(as.character(packageVersion("nflfastR")) == "6.0.0")
stopifnot(as.character(packageVersion("nflreadr")) == "1.5.1")
options(timeout = 300, nflreadr.cache = "memory")
manifest <- jsonlite::read_json(file.path(root, "run.json"), simplifyVector = TRUE)
fields <- c("player_id", "season", "season_type", "targets", "receptions", "receiving_yards",
            "receiving_tds", "receiving_yards_after_catch", "receiving_first_downs", "receiving_air_yards")
calculate <- function(plays) {
  if (nrow(plays) == 0L) return(data.frame())
  stats <- nflfastR::calculate_stats(pbp = plays, summary_level = "season",
                                    stat_type = "player", season_type = "REG")
  stopifnot(isTRUE(attr(stats, "custom_pbp")))
  as.data.frame(stats[fields])
}
controls <- list()
for (year in c(2009L, 2024L)) {
  name <- paste0("pbp-", year, ".rds")
  expected <- manifest$files[[name]]
  stopifnot(!is.null(expected), digest::digest(file = file.path(root, name),
              algo = "sha256", serialize = FALSE) == expected)
  pbp <- readRDS(file.path(root, name))
  pbp <- pbp[pbp$season_type %in% "REG" & !(pbp$two_point_attempt %in% 1), ]
  revisions <- setNames(list(expected), name)
  if (year == 2009L) {
    game <- pbp[pbp$game_id %in% "2009_01_PHI_CAR" & pbp$complete_pass %in% 1, ]
    # One actual missing depth/direction completion; two known pass contexts.
    selected <- c(which(game$play_id == 4173), which(game$pass_length %in% "short")[[1L]],
                  which(game$pass_length %in% "deep")[[1L]])
    plays <- game[selected, ]
    labels <- plays$pass_length
    buckets <- c("short", "deep")
    reason <- "missing original-pass depth"
    kind <- "missing_pass_context"
  } else {
    chart <- read.csv(chart_path)
    stopifnot(!anyDuplicated(chart[c("game_id", "play_id")]))
    pbp$source_order <- seq_len(nrow(pbp))
    joined <- merge(as.data.frame(pbp), chart[c("game_id", "play_id", "n_pass_rushers")],
                    by = c("game_id", "play_id"), all.x = TRUE, sort = FALSE)
    stopifnot(nrow(joined) == nrow(pbp))
    game <- joined[joined$game_id %in% "2024_07_HOU_GB" & joined$complete_pass %in% 1, ]
    game <- game[order(game$source_order), ]
    selected <- c(which(game$play_id == 981), which(game$n_pass_rushers %in% 1:4)[[1L]],
                  which(game$n_pass_rushers %in% 5:11)[[1L]])
    plays <- game[selected, ]
    rushers <- plays$n_pass_rushers
    labels <- ifelse(rushers %in% 1:4, "standard_rush",
                     ifelse(rushers %in% 5:11, "blitz", NA_character_))
    buckets <- c("standard_rush", "blitz")
    reason <- "rush count outside supported 1-11 range"
    kind <- "unusable_charting_field"
    revisions[[basename(chart_path)]] <- args[[3L]]
  }
  stopifnot(nrow(plays) == 3L, sum(is.na(labels)) == 1L)
  raw_buckets <- lapply(buckets, function(bucket) {
    stats <- calculate(plays[labels %in% bucket, ])
    stats$split_value <- bucket
    stats
  })
  whole <- calculate(plays)
  # Capture the exact upstream credit source loaded in this process. The fixture
  # is a provider-consistency control, not an independent NFL correctness claim.
  credit_path <- file.path(dirname(args[[4L]]), paste0("partition-control-credits-", year, ".rds"))
  saveRDS(nflfastR:::load_playstats(year), credit_path)
  revisions[[basename(credit_path)]] <- digest::digest(file = credit_path, algo = "sha256", serialize = FALSE)
  context_fields <- c("game_id", "play_id", "season", "season_type", "two_point_attempt",
                       "receiver_player_id", "receiver_player_name", "complete_pass",
                       "receiving_yards", "pass_length", "pass_location")
  if (year == 2024L) context_fields <- c(context_fields, "n_pass_rushers")
  membership <- plays[c("game_id", "play_id")]
  membership$split_value <- labels
  controls[[kind]] <- list(
    season = year, scope = "three selected real REG nonconversion completions; not season totals",
    versions = list(nflfastR = "6.0.0", nflreadr = "1.5.1"),
    source_revisions = revisions, missing_reason = reason, buckets = as.list(buckets),
    qualified_players = as.list(unique(plays$receiver_player_id)),
    context = as.data.frame(plays[context_fields]), membership = membership,
    bucket_stats = do.call(rbind, raw_buckets), classified = calculate(plays[!is.na(labels), ]),
    excluded = calculate(plays[is.na(labels), ]), overall = whole
  )
}
jsonlite::write_json(controls, args[[4L]], dataframe = "rows", na = "null", pretty = TRUE, auto_unbox = TRUE)
