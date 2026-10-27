# Passing preview using the unmodified official calculator and captured PBP.
# Rscript --vanilla producer.R OUTPUT; request.json is prepared by the Python job.
args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==1L)
out <- normalizePath(args[[1]],winslash="/",mustWork=TRUE)
source(file.path(out,"environment.R"))
lock <- verify_receiving_environment(file.path(out,"renv.lock"),Sys.getenv("NFL_RECEIVING_LIBRARY"))
request <- jsonlite::read_json(file.path(out,"request.json"),simplifyVector=TRUE)
input <- request$source_directory
year <- as.integer(request$season)
sha <- function(path) digest::digest(file=path,algo="sha256",serialize=FALSE)
stopifnot(identical(sha(file.path(input,"run.json")),request$source_run_sha256))
manifest <- jsonlite::read_json(file.path(input,"run.json"),simplifyVector=FALSE)
stopifnot(year %in% unlist(manifest$seasons),
          identical(sha(file.path(out,"renv.lock")),manifest$files[["renv.lock"]]))
stopifnot(as.character(packageVersion("nflfastR"))=="6.0.0",
          as.character(packageVersion("nflreadr"))=="1.5.1")
options(timeout=180,nflreadr.cache="memory")
read_capture <- function(kind) {
  name <- paste0(kind,"-",year,".rds")
  stopifnot(identical(sha(file.path(input,name)),manifest$files[[name]]))
  readRDS(file.path(input,name))
}
pbp <- read_capture("pbp")
weekly <- read_capture("weekly")
credits <- read_capture("credits")
reg <- pbp[pbp$season %in% year & pbp$season_type %in% "REG" & !(pbp$two_point_attempt %in% 1),]
stopifnot(nrow(reg)>0L,!anyDuplicated(reg[c("game_id","play_id")]))
fresh <- nflfastR:::load_playstats(year)
credit_keys <- c("game_id","play_id","gsis_player_id","stat_id","yards")
ordered <- function(x) {
  x <- as.data.frame(dplyr::arrange(dplyr::select(x,dplyr::all_of(credit_keys)),dplyr::across(dplyr::everything())))
  rownames(x) <- NULL
  x
}
# calculate_stats semi-joins detailed credits to supplied game/play keys.
# New games outside that subset must not invalidate a captured-input replay;
# changes to ANY supplied credit still fail, including duplicate multiplicity.
keys <- reg[c("game_id","play_id")]
stopifnot(isTRUE(all.equal(ordered(dplyr::semi_join(credits,keys,by=c("game_id","play_id"))),
                          ordered(dplyr::semi_join(fresh,keys,by=c("game_id","play_id"))),check.attributes=FALSE)))
saveRDS(fresh,file.path(out,"credits.rds"))
metrics <- c("attempts","completions","passing_yards","passing_tds","passing_interceptions","sacks_suffered")
extra <- c("passing_air_yards","passing_yards_after_catch","passing_first_downs","passing_epa","passing_cpoe")
selected <- c("player_id","season","season_type",metrics,extra)
write_frame <- function(x,name) write.csv(as.data.frame(x),file.path(out,name),row.names=FALSE,na="")
calculate <- function(x) {
  if(nrow(x)==0L)return(empty)
  stats <- nflfastR::calculate_stats(summary_level="season",stat_type="player",season_type="REG",pbp=x)
  stopifnot(isTRUE(attr(stats,"custom_pbp")))
  as.data.frame(stats[selected])
}
whole <- calculate(reg)
empty <- whole[0,]
write_frame(whole,"whole.csv")
keep <- reg$down %in% 1:4
write_frame(if(all(keep))whole else calculate(reg[keep,]),"classified.csv")
write_frame(calculate(reg[!keep,]),"excluded.csv")
down <- lapply(1:4,function(d) {
  frame <- calculate(reg[reg$down %in% d,])
  frame$split_value <- rep(as.character(d),nrow(frame))
  frame
})
write_frame(do.call(rbind,down),"down.csv")
context <- c("game_id","play_id","season","season_type","down","passer_player_id",
             "pass_attempt","sack","two_point_attempt")
write_frame(reg[context],"context.csv")
metric_context <- c(context,"play_type","complete_pass","incomplete_pass","interception",
                    "passing_yards","pass_touchdown","first_down","qb_epa","epa","cpoe",
                    "air_yards","yards_after_catch")
write_frame(reg[metric_context],"metric-context.csv")
write_frame(as.data.frame(fresh)[credit_keys],"metric-credits.csv")
stopifnot("game_id" %in% names(weekly))
reference <- weekly[weekly$season_type %in% "REG" & weekly$game_id %in% reg$game_id & !is.na(weekly$player_id),]
reference <- dplyr::summarise(dplyr::group_by(reference,player_id,season,season_type),
                            dplyr::across(dplyr::all_of(metrics),~sum(.x,na.rm=TRUE)),.groups="drop")
write_frame(reference,"weekly.csv")
verify_receiving_environment(file.path(out,"renv.lock"),Sys.getenv("NFL_RECEIVING_LIBRARY"))
files <- c("producer.R","environment.R","renv.lock","request.json","credits.rds","metric-context.csv","metric-credits.csv",
           "whole.csv","classified.csv","excluded.csv","down.csv","context.csv","weekly.csv")
hashes <- setNames(lapply(files,function(name)sha(file.path(out,name))),files)
jsonlite::write_json(list(format_version=2L,kind="passing_down_metrics_preview",season=year,
  R=as.character(getRversion()),nflfastR=as.character(packageVersion("nflfastR")),
  nflreadr=as.character(packageVersion("nflreadr")),files=hashes,
  credit_match_scope="supplied REG nonconversion game/play keys",
  source_run_sha256=request$source_run_sha256,fresh_credits_match_capture=TRUE),
  file.path(out,"run.json"),pretty=TRUE,auto_unbox=TRUE)
cat("PASSING DOWN EXPORT COMPLETE\n")
