# Replay comparison controls against a completed receiving capture; no downloads.
# Rscript r/test_upstream_inputs.R RECEIVING_RUN NEW_OUTPUT RSCRIPT LOCKED_LIBRARY
args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args) == 4L)
source_dir <- normalizePath(args[[1]],winslash='/',mustWork=TRUE)
root <- args[[2]]
rscript <- normalizePath(args[[3]],winslash='/',mustWork=TRUE)
library <- normalizePath(args[[4]],winslash='/',mustWork=TRUE)
.libPaths(c(library,.Library),include.site=FALSE)
stopifnot(!dir.exists(root));dir.create(root)
request <- jsonlite::read_json(file.path(source_dir,'upstream-request.json'),simplifyVector=FALSE)
files <- c('environment.R','renv.lock','upstream-verify.R','upstream-request.json',
           unlist(lapply(request$assets,function(item)c(item$download_file,item$consumed_file))))
results <- list()
for (fault in c('baseline','frame_metadata','value','credit_value','type','row_order','missing_column','wrong_season','wrong_hash')) {
 out <- file.path(root,fault);dir.create(out)
 stopifnot(all(file.copy(file.path(source_dir,files),out)))
 req <- request
 key <- if(fault=='credit_value') 'playstats' else 'pbp_rds'
 path <- file.path(out,req$assets[[key]]$consumed_file)
 frame <- readRDS(path)
 if(fault=='frame_metadata')attr(frame,'transport_metadata') <- 'different non-data wrapper'
 if(fault=='value')frame$epa[which(is.finite(frame$epa))[[1]]] <- frame$epa[which(is.finite(frame$epa))[[1]]] + 12345
 if(fault=='credit_value')frame$yards[which(is.finite(frame$yards))[[1]]] <- frame$yards[which(is.finite(frame$yards))[[1]]] + 12345
 if(fault=='type')frame$play_id <- as.character(frame$play_id)
 if(fault=='row_order')frame <- frame[nrow(frame):1,]
 if(fault=='missing_column')frame$epa <- NULL
 if(fault=='wrong_season')frame$season[] <- request$season - 1L
 if(!fault %in% c('baseline','wrong_hash')) {
   saveRDS(frame,path)
   req$assets[[key]]$consumed_sha256 <- digest::digest(file=path,algo='sha256',serialize=FALSE)
 }
 if(fault=='wrong_hash')req$assets[[key]]$consumed_sha256 <- paste(rep('0',64),collapse='')
 jsonlite::write_json(req,file.path(out,'upstream-request.json'),pretty=TRUE,auto_unbox=TRUE)
 status <- system2(rscript,c('--vanilla',shQuote(file.path(out,'upstream-verify.R')),shQuote(out),shQuote(library)),
                   stdout=file.path(out,'verification.log'),stderr=file.path(out,'verification.log'))
 expected <- fault %in% c('baseline','frame_metadata')
 stopifnot(identical(status==0L,expected))
 results[[fault]] <- list(expected_equal=expected,status=status,passed=TRUE)
}
jsonlite::write_json(results,file.path(root,'results.json'),pretty=TRUE,auto_unbox=TRUE)
cat('All nine real R comparator controls passed\n')
