"""Prepare and validate a separate database; publication is a separate step."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import duckdb


class CandidateError(RuntimeError):
    """The working copy is unsafe to build or failed preparation checks."""


def _wal(path: Path) -> Path:
    return Path(f'{path}.wal')


def _copy_source(source: Path, candidate: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(f'Source database does not exist: {source}')
    # A raw file copy cannot include uncheckpointed transactions safely. Opening
    # read-only also takes DuckDB's file lock, excluding other writer processes.
    if _wal(source).exists():
        raise CandidateError('Source has a WAL; close its writer before preparing a candidate')
    conn = duckdb.connect(str(source), read_only=True)
    try:
        if _wal(source).exists():
            raise CandidateError('Source has a WAL; close its writer before preparing a candidate')
        # Exclusive creation keeps an existing candidate (including a symlink)
        # intact. Only a file created by this run may be cleaned up on failure.
        with candidate.open('xb') as target:
            try:
                with source.open('rb') as origin:
                    shutil.copyfileobj(origin, target)
            except BaseException:
                target.close()
                candidate.unlink()
                raise
    finally:
        conn.close()


def _run_job(candidate: Path, module: str, arguments: list[str], *, read_only=False) -> None:
    env = os.environ.copy()
    # Set before importing ingest/config/builders: they share database._conn.
    env['NFL_DB_PATH'] = str(candidate)
    env['NFL_DB_READ_ONLY'] = '1' if read_only else '0'
    command = [sys.executable, '-m', module, *arguments]
    process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], env=env)
    try:
        code = process.wait()
    except BaseException:
        process.kill()
        process.wait()
        raise
    if code:
        raise subprocess.CalledProcessError(code, command)


def _run_worker(candidate: Path, seasons: list[int], *, core_inputs: Path | None = None) -> None:
    arguments = ['--seasons', *(str(s) for s in seasons)]
    if core_inputs is not None:
        arguments.extend(['--core-inputs', str(core_inputs)])
    _run_job(candidate, 'jobs.prepare_worker', arguments)


def _run_validation(candidate: Path) -> None:
    _run_job(candidate, 'jobs.validate', ['--database', str(candidate)], read_only=True)


def validate_preparation(candidate: Path, seasons: list[int]) -> None:
    """Check recorded downloads against core stored rows, not full release fitness."""
    if _wal(candidate).exists():
        raise CandidateError('Candidate still has a WAL; preparation did not close cleanly')
    conn = duckdb.connect(str(candidate), read_only=True)
    try:
        tables = {row[0] for row in conn.execute('SHOW TABLES').fetchall()}
        if 'snapshot_preparation' not in tables:
            raise CandidateError('Candidate has no preparation record')
        records = conn.execute(
            'SELECT format_version, requested_seasons, source_outcomes FROM snapshot_preparation'
        ).fetchall()
        if len(records) != 1 or records[0][0] != 1:
            raise CandidateError('Candidate has an invalid preparation record')
        if json.loads(records[0][1]) != seasons:
            raise CandidateError('Candidate preparation record has different requested seasons')
        outcomes = json.loads(records[0][2])

        def stored(table, season):
            if table not in tables:
                return 0
            return conn.execute(
                f'SELECT COUNT(*) FROM "{table}" WHERE season = ?', [season]
            ).fetchone()[0]

        def observed(source, season):
            matches = [o for o in outcomes if o['source'] == source and o['season'] == season]
            if len(matches) != 1:
                raise CandidateError(f'{source}[{season}]: expected one source outcome')
            return matches[0]

        def require_loaded(table, season):
            outcome = observed(table, season)
            if outcome['status'] != 'loaded' or outcome['rows'] <= 0:
                raise CandidateError(f'{table}[{season}]: required source was not loaded')
            if stored(table, season) != outcome['rows']:
                raise CandidateError(f'{table}[{season}]: stored count differs from downloaded count')

        for season in seasons:
            require_loaded('schedules', season)
            plays = observed('plays', season)
            if plays['status'] == 'loaded':
                for table in ('plays', 'rosters', 'weekly_player_stats'):
                    require_loaded(table, season)
                if stored('player_game_stats', season) == 0:
                    raise CandidateError(f'player_game_stats[{season}]: no prepared rows')
            elif plays['status'] != 'not_found' or stored('plays', season):
                raise CandidateError(f'plays[{season}]: cannot treat stored plays as an unplayed season')
    finally:
        conn.close()


def prepare_candidate(source: Path, candidate: Path, seasons: list[int], log=print, *,
                      core_inputs: Path | None = None) -> Path:
    """Copy a closed snapshot, prepare and validate in isolated processes.

    Never replaces source. Failed candidates are removed after the worker exits.
    Validation checks core rows, analytics, statistical identities and sampled API
    responses. Promotion and refresh watermark changes remain separate.
    """
    source, candidate = Path(source).resolve(), Path(candidate).absolute()
    if not seasons or any(type(s) is not int or s < 1999 for s in seasons):
        raise ValueError('Provide at least one integer season from 1999 onward')
    seasons = sorted(set(seasons))
    if core_inputs is not None:
        core_inputs = Path(core_inputs).resolve()
    if source == candidate.resolve():
        raise CandidateError('Source and candidate must be different paths')
    if candidate.exists() or candidate.is_symlink() or _wal(candidate).exists():
        raise FileExistsError(f'Candidate or its WAL already exists: {candidate}')
    candidate = candidate.resolve()
    log(f'Copying {source} to {candidate}')
    _copy_source(source, candidate)
    try:
        options = {} if core_inputs is None else {'core_inputs': core_inputs}
        _run_worker(candidate, seasons, **options)
        validate_preparation(candidate, seasons)
        _run_validation(candidate)
    except BaseException:
        candidate.unlink(missing_ok=True)
        _wal(candidate).unlink(missing_ok=True)
        raise
    log(f'Candidate validated: {candidate}; publication remains a separate step')
    return candidate
