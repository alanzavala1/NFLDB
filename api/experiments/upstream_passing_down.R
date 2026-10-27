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
data.table::setDTthreads(2L)
read_capture <- function(kind) {
  name <- paste0(kind,"-",year,".rds")
  stopifnot(identical(sha(file.path(input,name)),manifest$files[[name]]))
  readRDS(file.path(input,name))
}
pbp <- as.data.frame(read_capture("pbp"))
weekly <- as.data.frame(read_capture("weekly"))
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
cache <- new.env(parent=emptyenv())
calculate <- function(x) {
  if(nrow(x)==0L)return(empty)
  key <- digest::digest(x[c("game_id","play_id")],algo="sha256")
  if(exists(key,envir=cache,inherits=FALSE))return(get(key,envir=cache))
  cat("CALCULATE",nrow(x),"plays\n");flush.console()
  stats <- nflfastR::calculate_stats(summary_level="season",stat_type="player",season_type="REG",pbp=x)
  stopifnot(isTRUE(attr(stats,"custom_pbp")))
  value <- as.data.frame(stats[selected])
  assign(key,value,envir=cache)
  value
}
whole <- calculate(reg)
empty <- whole[0,]
write_frame(whole,"whole.csv")
all_views <- !is.null(request$dimensions)
dimensions <- if(all_views)unlist(request$dimensions) else "down"
partition_files <- c()
for(dimension in dimensions) {
  cat("VIEW",dimension,"START\n");flush.console()
  if(all_views) {
    source_dim <- switch(dimension,pass_depth="target_depth",pass_location="target_direction",dimension)
    name <- paste0("membership-",source_dim,"-",year,".csv")
    stopifnot(identical(sha(file.path(input,name)),manifest$files[[name]]))
    membership <- read.csv(file.path(input,name),na.strings="",colClasses=c("character","numeric","character"))
    stopifnot(nrow(membership)==nrow(reg),!anyDuplicated(membership[c("game_id","play_id")]))
    source_keys <- paste(membership$game_id,membership$play_id,sep="/")
    index <- match(paste(reg$game_id,reg$play_id,sep="/"),source_keys)
    stopifnot(!anyNA(index))
    labels <- membership$split_value[index]
    definitions <- jsonlite::read_json(file.path(input,"definitions.json"),simplifyVector=FALSE)
    buckets <- unlist(definitions$dimensions[[source_dim]])
    stopifnot(length(buckets)>0L,all(labels[!is.na(labels)] %in% buckets))
    membership <- as.data.frame(reg[c("game_id","play_id")])
    membership$split_value <- labels
    name <- paste0("membership-",dimension,".csv")
    write_frame(membership,name)
    partition_files <- c(partition_files,name)
  } else {
    labels <- ifelse(reg$down %in% 1:4,as.character(reg$down),NA_character_)
    buckets <- as.character(1:4)
  }
  keep <- !is.na(labels)
  classified_name <- if(all_views)paste0("classified-",dimension,".csv") else "classified.csv"
  excluded_name <- if(all_views)paste0("excluded-",dimension,".csv") else "excluded.csv"
  write_frame(calculate(reg[keep,]),classified_name)
  write_frame(calculate(reg[!keep,]),excluded_name)
  values <- lapply(buckets,function(bucket) {
    frame <- calculate(reg[labels %in% bucket,])
    frame$split_value <- rep(bucket,nrow(frame))
    frame
  })
  name <- paste0(dimension,".csv")
  write_frame(do.call(rbind,values),name)
  partition_files <- c(partition_files,classified_name,excluded_name,name)
  cat("VIEW",dimension,"DONE\n");flush.console()
}
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
           "whole.csv","context.csv","weekly.csv",partition_files)
hashes <- setNames(lapply(files,function(name)sha(file.path(out,name))),files)
jsonlite::write_json(list(format_version=if(all_views)3L else 2L,
  kind=if(all_views)"passing_splits_preview" else "passing_down_metrics_preview",season=year,
  dimensions=as.list(dimensions),
  R=as.character(getRversion()),nflfastR=as.character(packageVersion("nflfastR")),
  nflreadr=as.character(packageVersion("nflreadr")),files=hashes,
  credit_match_scope="supplied REG nonconversion game/play keys",
  source_run_sha256=request$source_run_sha256,fresh_credits_match_capture=TRUE),
  file.path(out,"run.json"),pretty=TRUE,auto_unbox=TRUE)
cat("PASSING EXPORT COMPLETE\n")
