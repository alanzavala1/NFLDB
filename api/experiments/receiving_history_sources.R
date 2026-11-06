args <- commandArgs(trailingOnly = TRUE)
stopifnot(length(args) == 2L)
root <- normalizePath(args[[1L]], winslash = "/", mustWork = TRUE)
source(file.path(root, "environment.R"))
verify_receiving_environment(file.path(root, "renv.lock"), args[[2L]])
manifest <- jsonlite::read_json(file.path(root, "run.json"), simplifyVector = TRUE)
audit <- file.path(root, "audit")
if (dir.exists(audit)) stop("Audit directory already exists")
dir.create(audit)
for (year in unlist(manifest$seasons)) {
  for (name in paste0(c("pbp-", "weekly-", "credits-"), year, ".rds")) {
    stopifnot(digest::digest(file = file.path(root, name), algo = "sha256", serialize = FALSE) == manifest$files[[name]])
  }
  pbp <- as.data.frame(readRDS(file.path(root, paste0("pbp-", year, ".rds"))))
  reg <- pbp[pbp$season_type %in% "REG" & !(pbp$two_point_attempt %in% 1), ]
  context <- read.csv(file.path(root, paste0("context-", year, ".csv")))
  fields <- setdiff(names(context), c("is_play_action", "n_pass_rushers", "ftn_matched"))
  write.csv(reg[fields], file.path(audit, paste0("context-", year, ".csv")), row.names = FALSE, na = "")
  attempts <- reg[(reg$complete_pass %in% 1 | reg$incomplete_pass %in% 1 | reg$interception %in% 1) & !is.na(reg$receiver_player_id), ]
  counts <- as.data.frame(table(attempts$receiver_player_id), stringsAsFactors = FALSE)
  names(counts) <- c("player_id", "qualifying_plays")
  counts <- counts[counts$qualifying_plays >= 25, ]
  write.csv(counts, file.path(audit, paste0("qualified-", year, ".csv")), row.names = FALSE)
  credits <- as.data.frame(readRDS(file.path(root, paste0("credits-", year, ".rds"))))
  write.csv(credits[c("game_id", "play_id", "team_abbr", "gsis_player_id", "stat_id", "yards")],
            file.path(audit, paste0("credits-", year, ".csv")), row.names = FALSE, na = "")
  # Download an independent game-coverage reference and retain its exact bytes.
  games <- as.data.frame(nflreadr::load_schedules(year))
  saveRDS(games, file.path(audit, paste0("schedules-", year, ".rds")))
  write.csv(games[c("game_id", "season", "game_type", "gameday", "home_score", "away_score")],
            file.path(audit, paste0("schedules-", year, ".csv")), row.names = FALSE, na = "")
}
files <- list.files(audit)
hashes <- setNames(lapply(files, function(name) digest::digest(file = file.path(audit, name), algo = "sha256", serialize = FALSE)), files)
jsonlite::write_json(list(source_manifest_sha256 = digest::digest(file = file.path(root, "run.json"), algo = "sha256", serialize = FALSE),
                         files = hashes), file.path(audit, "run.json"), pretty = TRUE, auto_unbox = TRUE)
cat("Source audit prepared:", root, "\n")
