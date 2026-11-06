"""Compose captured receiving runs without merging or recalculating their data."""
import hashlib
import json
from pathlib import Path

from pipeline.receiving_core_inputs import ReceivingCoreInputs, load_scoped_feeds
from pipeline.receiving_preview import file_sha256
from pipeline.receiving_splits import validate_export_manifest
from pipeline.source_results import SourceError
from pipeline.capture_paths import capture_directory


def _policy(inputs: ReceivingCoreInputs) -> tuple:
    """Different seasons may share a build only under one captured calculation policy."""
    hashes = [inputs.manifest["files"].get(name) for name in
              ("bridge.R", "environment.R", "renv.lock", "columns.json")]
    source_names = ("producer.R", "definitions.json")
    hashes.extend(inputs.receiving_manifest["files"].get(name) for name in source_names)
    if any(not isinstance(digest, str) or len(digest) != 64 for digest in hashes):
        raise SourceError("receiving_core_inputs", None, "collection needs captured producer/environment revisions")
    if any(file_sha256(inputs.source / name) != inputs.receiving_manifest["files"][name]
           for name in source_names):
        raise SourceError("receiving_core_inputs", None, "captured calculator policy changed")
    for year in inputs.seasons:
        validate_export_manifest(inputs.receiving_manifest, year)
    return tuple(hashes)


def _owners(bundles: list[ReceivingCoreInputs]) -> dict[int, ReceivingCoreInputs]:
    if not bundles:
        raise SourceError("receiving_core_inputs", None, "provide at least one captured bundle")
    policy, owners = _policy(bundles[0]), {}
    for bundle in bundles:
        if _policy(bundle) != policy:
            raise SourceError("receiving_core_inputs", None, "collection mixes calculator/conversion policies")
        for year in bundle.seasons:
            if year in owners:
                raise SourceError("receiving_core_inputs", year, "multiple bundles claim the same season")
            owners[year] = bundle
    return owners


class ReceivingCoreCollection:
    """Immutable index of disjoint, compatible, revision-bound source bundles."""

    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        data = (self.directory / "run.json").read_bytes()
        self.manifest_sha256 = hashlib.sha256(data).hexdigest()
        self.manifest = json.loads(data)
        if (not isinstance(self.manifest, dict)
                or type(self.manifest.get("format_version")) is not int
                or self.manifest.get("format_version") != 2
                or self.manifest.get("kind") != "receiving_core_collection"
                or not isinstance(self.manifest.get("bundles"), list)):
            raise SourceError("receiving_core_inputs", None, "unsupported collection index")
        bundles = []
        for entry in self.manifest["bundles"]:
            path = capture_directory(self.directory, entry["directory"])
            bundle = ReceivingCoreInputs(path)
            if bundle.manifest_sha256 != entry["manifest_sha256"] or bundle.seasons != entry["seasons"]:
                raise SourceError("receiving_core_inputs", None, "indexed bundle revision/seasons changed")
            bundles.append(bundle)
        self.owners = _owners(bundles)
        self.seasons = sorted(self.owners)
        if self.manifest.get("seasons") != self.seasons:
            raise SourceError("receiving_core_inputs", None, "collection season coverage differs from bundles")

    def load_feeds(self, play_seasons: list[int], weekly_seasons: list[int]):
        if file_sha256(self.directory / "run.json") != self.manifest_sha256:
            raise SourceError("receiving_core_inputs", None, "collection index changed")
        for entry in self.manifest["bundles"]:
            if file_sha256(capture_directory(self.directory, entry["directory"]) / "run.json") != entry["manifest_sha256"]:
                raise SourceError("receiving_core_inputs", None, "indexed bundle revision changed")
        return load_scoped_feeds(lambda year: self.owners[year].feeds([year]),
                                 play_seasons, weekly_seasons, self.seasons)

    def feeds(self, seasons: list[int]):
        return self.load_feeds(seasons, seasons)

    def receiving_run(self, season: int) -> tuple[Path, dict, str]:
        if season not in self.owners:
            raise SourceError("receiving_core_inputs", season, "no captured receiving run")
        return self.owners[season].receiving_run(season)

    def revision(self) -> str:
        return f"receiving core collection SHA256 {self.manifest_sha256} ({len(self.seasons)} seasons)"


def open_core_inputs(directory: Path) -> ReceivingCoreInputs | ReceivingCoreCollection:
    """Serving-independent reader for a single run or a completed collection."""
    manifest = json.loads((directory / "run.json").read_bytes())
    if isinstance(manifest, dict) and manifest.get("kind") == "receiving_core_collection":
        return ReceivingCoreCollection(directory)
    return ReceivingCoreInputs(directory)


def assemble_core_inputs(directories: list[Path], output: Path, *, log=print) -> ReceivingCoreCollection:
    """Validate every source season, then create a new index; leave inputs intact."""
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    bundles = [ReceivingCoreInputs(path) for path in directories]
    owners = _owners(bundles)
    entries = [{"directory": str(bundle.directory), "manifest_sha256": bundle.manifest_sha256,
                "seasons": bundle.seasons} for bundle in sorted(bundles, key=lambda item: item.seasons[0])]
    for year, bundle in sorted(owners.items()):
        plays, weekly = bundle.feeds([year])
        log(f"Validated captured {year}: {len(plays.data):,} plays, {len(weekly.data):,} weekly rows")
    record = {"format_version": 2, "kind": "receiving_core_collection",
              "seasons": sorted(owners), "bundles": entries}
    output.mkdir()
    marker = output / "run.json"
    try:
        with marker.open("xb") as stream:
            stream.write(json.dumps(record, indent=2, sort_keys=True).encode())
        return ReceivingCoreCollection(output)
    except BaseException:
        marker.unlink(missing_ok=True)
        raise
