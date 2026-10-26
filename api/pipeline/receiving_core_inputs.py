"""Reuse the receiving calculator's captured full inputs in ordinary ingestion.

R conversion is an explicit offline action. Reading a bundle never starts R,
downloads data or opens a database. This does not promote receiving preview rows.
"""
import io
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess

import numpy as np
import pandas as pd

from pipeline.receiving_preview import file_sha256
from pipeline.receiving_splits import read_export_bytes, read_export_csv, validate_export_manifest
from pipeline.source_results import SeasonalFeed, SourceError
from pipeline.sources import PLAYS_KEEP_COLUMNS, WEEKLY_REQUIRED_COLUMNS


def load_scoped_feeds(reader, play_seasons: list[int], weekly_seasons: list[int], available: list[int]):
    """Validate one season at a time; retain only the plays actually requested.

    A weekly-schema migration may need decades of stats for a one-season play
    refresh. Do not concatenate all that historical PBP just to discard it.
    """
    wanted = set(play_seasons) | set(weekly_seasons)
    if not wanted or any(type(year) is not int or year not in available for year in wanted):
        raise SourceError("receiving_core_inputs", None,
                          f"bundle must cover every requested season; available {available}, requested {sorted(wanted)}")
    plays, weekly = [], []
    for year in sorted(wanted):
        play_feed, weekly_feed = reader(year)
        if year in play_seasons:
            plays.append(play_feed.data)
        if year in weekly_seasons:
            weekly.append(weekly_feed.data)
    def feed(frames, seasons):
        return SeasonalFeed(pd.concat(frames, ignore_index=True) if frames else None, sorted(set(seasons)), [])
    return feed(plays, play_seasons), feed(weekly, weekly_seasons)


def _read_table(directory: Path, manifest: dict, name: str, season: int) -> pd.DataFrame:
    record = manifest["tables"][name]
    types = {"character": "string", "integer": "Int64", "double": "float64", "logical": "boolean"}
    if not record["columns"] or set(record["columns"].values()) - types.keys():
        raise SourceError("receiving_core_inputs", season, "unsupported captured column types")
    data = read_export_bytes(directory, manifest, name, season=season)
    frame = pd.read_csv(io.BytesIO(data), keep_default_na=False,
                        na_values=[manifest["missing_value"]],
                        dtype={column: types[kind] for column, kind in record["columns"].items()},
                        true_values=["TRUE"], false_values=["FALSE"])
    if list(frame.columns) != list(record["columns"]) or len(frame) != record["rows"] or frame.empty:
        raise SourceError("receiving_core_inputs", season, "captured table schema/count mismatch")
    if frame.season.isna().any() or not frame.season.eq(season).all():
        raise SourceError("receiving_core_inputs", season, "captured table contains unexpected seasons")
    return frame


def _same_rows(actual: pd.DataFrame, expected: pd.DataFrame, keys: list[str], season: int) -> None:
    """Match scope and values before applying the main loader's float32 policy."""
    if actual.duplicated(keys).any() or expected.duplicated(keys).any():
        raise SourceError("receiving_core_inputs", season, "duplicate captured reference keys")
    actual = actual.set_index(keys).sort_index()
    expected = expected.set_index(keys).sort_index()
    try:
        for column in expected:
            if pd.api.types.is_numeric_dtype(expected[column]):
                actual[column] = pd.to_numeric(actual[column], errors="raise").astype("float64")
                expected[column] = expected[column].astype("float64")
            else:
                actual[column] = actual[column].astype("string").replace("", pd.NA)
                expected[column] = expected[column].astype("string").replace("", pd.NA)
        pd.testing.assert_frame_equal(actual[expected.columns], expected, check_dtype=False,
                                      check_index_type=False, rtol=1e-12, atol=1e-12)
    except (AssertionError, ValueError, TypeError) as error:
        raise SourceError("receiving_core_inputs", season, "captured inputs differ from receiving references") from error


class ReceivingCoreInputs:
    """Hash-bound plays/weekly feeds; require every requested season, never refetch."""

    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        manifest_bytes = (self.directory / "run.json").read_bytes()
        self.manifest = json.loads(manifest_bytes)
        if (not isinstance(self.manifest, dict)
                or type(self.manifest.get("format_version")) is not int
                or self.manifest.get("format_version") != 1
                or self.manifest.get("missing_value") != "__NFLDB_MISSING_VALUE__"):
            raise SourceError("receiving_core_inputs", None, "unsupported input bundle")
        self.manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
        data = read_export_bytes(self.directory, self.manifest, "receiving-run.json", season=0)
        self.receiving_manifest = json.loads(data)
        self.source = Path(self.manifest["source_directory"])
        years = self.manifest.get("seasons")
        if (not isinstance(years, list) or not years
                or any(type(year) is not int or year < 1999 for year in years)
                or len(set(years)) != len(years)
                or years != self.receiving_manifest.get("seasons")):
            raise SourceError("receiving_core_inputs", None, "bundle seasons differ from receiving run")
        self.seasons = sorted(years)
        if file_sha256(self.source / "run.json") != self.manifest["files"]["receiving-run.json"]:
            raise SourceError("receiving_core_inputs", None, "receiving completion record changed")
        for name in ("bridge.R", "environment.R", "renv.lock", "columns.json"):
            read_export_bytes(self.directory, self.manifest, name, season=0)

    def feeds(self, seasons: list[int]) -> tuple[SeasonalFeed, SeasonalFeed]:
        if (file_sha256(self.directory / "run.json") != self.manifest_sha256
                or file_sha256(self.source / "run.json") != self.manifest["files"]["receiving-run.json"]):
            raise SourceError("receiving_core_inputs", None, "input completion record changed")
        if not seasons or any(type(year) is not int or year not in self.manifest["seasons"] for year in seasons):
            raise SourceError("receiving_core_inputs", None,
                              f"bundle must cover every requested season; available {self.manifest['seasons']}, requested {seasons}")
        plays, weekly = [], []
        for year in dict.fromkeys(seasons):
            validate_export_manifest(self.receiving_manifest, year)
            frames = []
            for kind, origin in (("plays", "pbp"), ("weekly", "weekly")):
                name = f"{kind}-{year}.csv"
                record = self.manifest["tables"][name]
                source_name = f"{origin}-{year}.rds"
                if (record["source"] != source_name
                        or record["source_sha256"] != self.receiving_manifest["files"].get(source_name)
                        or file_sha256(self.source / source_name) != record["source_sha256"]):
                    raise SourceError("receiving_core_inputs", year, "captured source revision changed")
                frames.append(_read_table(self.directory, self.manifest, name, year))
            pbp, stats = frames
            required = {"game_id", "play_id", "week", "season_type", "two_point_attempt"}
            if required - set(pbp) or set(WEEKLY_REQUIRED_COLUMNS) - set(stats):
                raise SourceError("receiving_core_inputs", year, "captured input missing required columns")
            if pbp[["game_id", "play_id"]].isna().any().any() or pbp.duplicated(["game_id", "play_id"]).any():
                raise SourceError("receiving_core_inputs", year, "invalid captured play identity")
            context = read_export_csv(self.source, self.receiving_manifest, f"context-{year}.csv", season=year)
            fields = context.columns.difference(["is_play_action", "n_pass_rushers", "ftn_matched"])
            if set(fields) - set(pbp):
                raise SourceError("receiving_core_inputs", year, "captured plays missing receiving context fields")
            reg = pbp.loc[pbp.season_type.eq("REG") & ~pbp.two_point_attempt.eq(1).fillna(False)]
            _same_rows(reg[list(fields)].copy(), context[list(fields)].copy(), ["game_id", "play_id"], year)
            reference = read_export_csv(self.source, self.receiving_manifest, f"weekly-{year}.csv", season=year)
            _same_rows(stats.loc[stats.season_type.eq("REG"), list(reference)].copy(), reference,
                       ["player_id", "season", "season_type", "week"], year)
            # Same projection/precision policy as fetch_play_by_play; conversion
            # plays and postseason rows remain in the core, unlike split context.
            pbp = pbp[[column for column in PLAYS_KEEP_COLUMNS if column in pbp]].copy()
            floats = pbp.select_dtypes(include=["float64"]).columns
            pbp[floats] = pbp[floats].astype("float32")
            if not np.isfinite(pbp[floats].to_numpy()[pbp[floats].notna().to_numpy()]).all():
                raise SourceError("receiving_core_inputs", year, "nonfinite/overflowed captured play values")
            plays.append(pbp)
            weekly.append(stats)
        years = list(dict.fromkeys(seasons))
        return (SeasonalFeed(pd.concat(plays, ignore_index=True), years, []),
                SeasonalFeed(pd.concat(weekly, ignore_index=True), years, []))

    def revision(self) -> str:
        return f"receiving core bundle SHA256 {self.manifest_sha256}; receiving run SHA256 {self.manifest['files']['receiving-run.json']}"

    def load_feeds(self, play_seasons: list[int], weekly_seasons: list[int]):
        return load_scoped_feeds(lambda year: self.feeds([year]), play_seasons, weekly_seasons, self.seasons)

    def receiving_run(self, season: int) -> tuple[Path, dict, str]:
        if season not in self.seasons:
            raise SourceError("receiving_core_inputs", season, "no captured receiving run")
        read_export_bytes(self.directory, self.manifest, "receiving-run.json", season=season)
        return self.source, self.receiving_manifest, self.manifest["files"]["receiving-run.json"]


def export_core_inputs(exports: Path, output: Path, *, rscript: Path, library: Path) -> ReceivingCoreInputs:
    """Convert existing full RDS captures once; preserve source exports and DBs."""
    exports, output = exports.resolve(), output.absolute()
    rscript, library = rscript.resolve(), library.resolve()
    if not rscript.is_file() or not library.is_dir():
        raise ValueError("Provide an existing Rscript executable and locked library")
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    manifest_bytes = (exports / "run.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    for year in manifest["seasons"]:
        validate_export_manifest(manifest, year)
    output.mkdir()
    api = Path(__file__).resolve().parents[1]
    for name, data in (("bridge.R", (api / "r/receiving_core_inputs.R").read_bytes()),
                       ("receiving-run.json", manifest_bytes),
                       ("columns.json", json.dumps({"plays": PLAYS_KEEP_COLUMNS}).encode()),
                       *((name, read_export_bytes(exports, manifest, name, season=0))
                         for name in ("environment.R", "renv.lock"))):
        with (output / name).open("xb") as stream:
            stream.write(data)
    env = os.environ.copy()
    env.update(R_LIBS_USER=str(library), NFL_RECEIVING_LIBRARY=str(library), LC_ALL="C")
    options = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
    with (output / "R-job.log").open("xb") as log:
        process = subprocess.Popen([str(rscript), "--vanilla", str(output / "bridge.R"),
                                    str(exports), str(output), str(library)],
                                   env=env, stdout=log, stderr=subprocess.STDOUT, **options)
        try:
            code = process.wait()
        except BaseException:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise
    if code:
        raise SourceError("receiving_core_inputs", None, f"R conversion failed; see {output / 'R-job.log'}")
    inputs = ReceivingCoreInputs(output)
    inputs.feeds(manifest["seasons"])
    return inputs
