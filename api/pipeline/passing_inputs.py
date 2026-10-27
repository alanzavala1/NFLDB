"""Immutable index of complete native passing exports; never calculates or downloads."""
import hashlib
import json
from pathlib import Path

from pipeline.passing_exports import load_passing_season, passing_policy
from pipeline.receiving_preview import file_sha256
from pipeline.source_results import SourceError


class PassingInputs:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        data = (self.directory / "run.json").read_bytes()
        self.manifest_sha256 = hashlib.sha256(data).hexdigest()
        self.manifest = json.loads(data)
        records = self.manifest.get("exports")
        if (self.manifest.get("format_version") != 1 or type(self.manifest.get("format_version")) is not int
                or self.manifest.get("kind") != "passing_export_collection" or not isinstance(records, list) or not records):
            raise SourceError("passing_inputs", None, "unsupported passing collection")
        self.exports = {}
        for record in records:
            year, path, digest = record.get("season"), Path(record["directory"]), record.get("manifest_sha256")
            if (type(year) is not int or year < 1999 or year in self.exports or not path.is_absolute()
                    or not isinstance(digest, str) or len(digest) != 64 or file_sha256(path / "run.json") != digest):
                raise SourceError("passing_inputs", year, "invalid/changed indexed passing export")
            self.exports[year] = (path, digest)
        self.seasons = sorted(self.exports)
        if self.manifest.get("seasons") != self.seasons or self.manifest.get("policy") != passing_policy():
            raise SourceError("passing_inputs", None, "passing season coverage or calculator policy changed")

    def load(self, season, core_inputs):
        if file_sha256(self.directory / "run.json") != self.manifest_sha256 or season not in self.exports:
            raise SourceError("passing_inputs", season, "changed collection or missing season")
        path, digest = self.exports[season]
        if file_sha256(path / "run.json") != digest:
            raise SourceError("passing_inputs", season, "indexed passing completion changed")
        return load_passing_season(path, core_inputs, season)

    def revision(self):
        return f"passing export collection SHA256 {self.manifest_sha256} ({len(self.seasons)} seasons)"


def assemble_passing_inputs(directories, output, core_inputs, *, log=print):
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    records = []
    for directory in directories:
        directory = directory.resolve()
        manifest = json.loads((directory / "run.json").read_bytes())
        year = manifest.get("season")
        if type(year) is not int or year < 1999 or any(record["season"] == year for record in records):
            raise SourceError("passing_inputs", year, "invalid or duplicate indexed season")
        digest = file_sha256(directory / "run.json")
        prepared = load_passing_season(directory, core_inputs, year)
        if file_sha256(directory / "run.json") != digest:
            raise SourceError("passing_inputs", year, "completion changed during validation")
        records.append(dict(season=year, directory=str(directory), manifest_sha256=digest))
        log(f"Passing[{year}]: {prepared.report['rows']:,} rows, all views validated")
    if not records:
        raise ValueError("Provide at least one complete passing export")
    records.sort(key=lambda record: record["season"])
    output.mkdir()
    record = dict(format_version=1, kind="passing_export_collection", policy=passing_policy(),
                  seasons=[record["season"] for record in records], exports=records)
    (output / "run.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return PassingInputs(output)
