"""Build a separate receiving preview; never promote it or change live splits."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import uuid

import duckdb

from pipeline.snapshots import CandidateError, _copy_source, _run_job, _wal


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _run_export(rscript: Path, library: Path, output: Path, seasons: list[int], run_id: str) -> None:
    api = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(R_LIBS_USER=str(library), LC_ALL="C", NFL_RECEIVING_RUN_ID=run_id)
    command = [str(rscript), "--vanilla", str(api / "experiments/upstream_receiving_splits.R"),
               str(output), *(str(year) for year in seasons)]
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    with (output / "R-job.log").open("xb") as log:
        process = subprocess.Popen(command, cwd=api, env=env, stdout=log, stderr=subprocess.STDOUT, **options)
        try:
            code = process.wait()
        except BaseException:
            # Rscript can launch another process. Stop this job's process tree
            # before its candidate is cleaned up, including on Windows.
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise
    if code:
        raise CandidateError(f"R export failed ({code}); see {output / 'R-job.log'}")


def prepare_receiving_preview(source: Path, candidate: Path, output: Path,
                               seasons: list[int], *, rscript: Path, library: Path,
                               log=print) -> dict:
    """Copy a closed source, run official R, then prepare a preview in a worker.

    The new DB contains Down/quarter preview tables, not replacement player_splits.
    Failed owned candidates are removed; export logs remain for inspection.
    Existing paths are refused. This is not the full candidate acceptance gate.
    """
    source, candidate, output = source.resolve(), candidate.absolute(), output.absolute()
    rscript, library = rscript.resolve(), library.resolve()
    if not seasons or any(type(year) is not int or year < 1999 for year in seasons):
        raise ValueError("Provide integer seasons from 1999 onward")
    seasons = sorted(set(seasons))
    if candidate.resolve() == source:
        raise CandidateError("Source and preview must be different paths")
    if candidate.exists() or candidate.is_symlink() or _wal(candidate).exists():
        raise FileExistsError(f"Preview or its WAL already exists: {candidate}")
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"Export directory already exists: {output}")
    if not rscript.is_file() or not library.is_dir():
        raise CandidateError("Provide an existing Rscript executable and R library")
    candidate = candidate.resolve()
    _copy_source(source, candidate)
    try:
        output.mkdir()
        baseline = file_sha256(candidate)
        run_id = uuid.uuid4().hex
        log(f"Running official R export for {seasons}; log: {output / 'R-job.log'}")
        _run_export(rscript, library, output, seasons, run_id)
        _run_job(candidate, "jobs.receiving_preview_worker", [
            "--source", str(source), "--exports", str(output), "--run-id", run_id,
            "--baseline-sha256", baseline, "--seasons", *(str(year) for year in seasons),
        ])
        if _wal(candidate).exists():
            raise CandidateError("Preview worker left a WAL")
        with duckdb.connect(str(candidate), read_only=True) as conn:
            records = conn.execute("SELECT record FROM receiving_preview_preparation").fetchall()
        if len(records) != 1:
            raise CandidateError("Preview requires exactly one preparation record")
        report = json.loads(records[0][0])
        if report.get("run_id") != run_id or report.get("status") != "preview_only":
            raise CandidateError("Preview completion record does not match this job")
    except BaseException:
        candidate.unlink(missing_ok=True)
        _wal(candidate).unlink(missing_ok=True)
        raise
    log(f"Receiving preview complete: {candidate}; not accepted for publication")
    return report
