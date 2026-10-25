"""Independent receiving-preview audit; never authorizes snapshot publication.

Consumes hash-bound R exports and an isolated candidate. Checks full game
coverage separately from agreement on the plays the provider actually supplied.
"""
import argparse
import json
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
import subprocess

import duckdb
import pandas as pd

from pipeline.receiving_dimensions import DIMENSIONS, context_split_values
from pipeline.receiving_partition_validation import COUNT_FIELDS
from pipeline.receiving_preview import file_sha256
from pipeline.receiving_splits import read_export_csv
from pipeline.validation import SnapshotValidationError, validate_snapshot
from services.receiving_coverage import targets_unavailable, air_yards_unavailable

if not __debug__:
    raise RuntimeError("Run the audit without Python -O; validation assertions must stay enabled")


def _success_percent(successes: int, targets: int) -> float:
    return float((Decimal(int(successes) * 100) / Decimal(int(targets))).quantize(
        Decimal("0.1"), rounding=ROUND_HALF_EVEN))

def audit(root: Path, candidate: Path, year: int, *, source: Path) -> dict:
    """Audit complete exports; a source gap remains a failed completeness check."""
    baseline = file_sha256(source)
    manifest = json.loads((root / "run.json").read_text())
    assert manifest["seasons"] == [year]
    for name, digest in manifest["files"].items():
        assert file_sha256(root / name) == digest, name
    raw_root = root / "audit"
    raw_manifest = json.loads((raw_root / "run.json").read_text())
    assert raw_manifest["source_manifest_sha256"] == file_sha256(root / "run.json")
    for name, digest in raw_manifest["files"].items():
        assert file_sha256(raw_root / name) == digest, name
    assert not Path(str(source) + ".wal").exists()
    assert not Path(str(candidate) + ".wal").exists()
    context = read_export_csv(root, manifest, f"context-{year}.csv", season=year)
    raw_context = pd.read_csv(raw_root / f"context-{year}.csv", low_memory=False)
    joined = context.merge(raw_context, on=["game_id", "play_id"], validate="one_to_one", suffixes=("", "_raw"))
    assert len(joined) == len(context) == len(raw_context)
    text_fields = set(context.select_dtypes(include=["object", "str", "string"]).columns)
    for field in raw_context.columns.drop(["game_id", "play_id"]):
        a, b = joined[field], joined[f"{field}_raw"]
        if field in text_fields:
            a, b = a.astype("string"), b.astype("string")
        assert (a.eq(b).fillna(False) | (a.isna() & b.isna())).all(), (year, field)
    schedules = pd.read_csv(raw_root / f"schedules-{year}.csv")
    completed = schedules.loc[schedules.game_type.eq("REG") & schedules.home_score.notna() & schedules.away_score.notna()]
    missing_games = sorted(set(completed.game_id) - set(context.game_id))
    extra_games = sorted(set(context.game_id) - set(completed.game_id))
    qualified = pd.read_csv(raw_root / f"qualified-{year}.csv")
    independent_counts = dict(zip(qualified.player_id, qualified.qualifying_plays))
    credits = pd.read_csv(raw_root / f"credits-{year}.csv")
    credits = credits.merge(context[["game_id", "play_id"]], on=["game_id", "play_id"], validate="many_to_one")
    keys = ["game_id", "play_id", "team_abbr"]
    team_air = credits.loc[credits.stat_id.isin([111, 112])].groupby(keys).yards.sum().rename("team_air")
    team_first = credits.loc[credits.stat_id.eq(4)].groupby(keys).size().gt(0).rename("team_first")
    credits = credits.join(team_air, on=keys).join(team_first, on=keys)
    credits["targets"] = credits.stat_id.eq(115).astype(int)
    credits["receptions"] = credits.stat_id.isin([21, 22]).astype(int)
    credits["receiving_yards"] = credits.yards.where(credits.stat_id.isin([21, 22, 23, 24]), 0)
    credits["receiving_tds"] = credits.stat_id.isin([22, 24]).astype(int)
    credits["receiving_yards_after_catch"] = credits.yards.where(credits.stat_id.eq(113), 0)
    credits["receiving_first_downs"] = (credits.receptions.eq(1) & credits.team_first.fillna(False)).astype(int)
    credits["receiving_air_yards"] = credits.team_air.fillna(0).where(credits.stat_id.eq(115), 0)
    report = {"season": year, "status": "source_gap" if missing_games or extra_games else "passed",
              "auditor_sha256": file_sha256(Path(__file__)),
              "games": context.game_id.nunique(), "expected_games": len(completed),
              "missing_game_ids": missing_games, "unconfirmed_game_ids": extra_games,
              "full_game_coverage": not missing_games and not extra_games,
              "latest_game": str(completed.gameday.max()),
              "context_plays": len(context), "qualified_players": len(independent_counts),
              "verified_files": len(manifest["files"]), "source_sha256": baseline,
              "manifest_sha256": file_sha256(root / "run.json"), "audit_sha256": file_sha256(raw_root / "run.json"), "views": {}}
    with duckdb.connect(str(candidate), read_only=True) as conn:
        proof = json.loads(conn.execute("SELECT record FROM receiving_preview_preparation").fetchone()[0])
        assert proof["format_version"] == 4 and proof["status"] == "preview_only"
        assert proof["source_sha256"] == baseline and proof["export_manifest_sha256"] == report["manifest_sha256"]
        assert proof["qualifications"][str(year)]["qualifying_plays"] == independent_counts
        assert proof["whole_references"][str(year)]["production_matches_weekly"]
        source_sql = str(source.resolve()).replace("'", "''")
        conn.execute(f"ATTACH '{source_sql}' AS original (READ_ONLY)")
        for a, b in (("main", "original"), ("original", "main")):
            assert conn.execute(f"SELECT COUNT(*) FROM (SELECT * FROM {a}.player_splits EXCEPT ALL SELECT * FROM {b}.player_splits)").fetchone()[0] == 0
        for dim in DIMENSIONS:
            labels = context_split_values(context, dim, year)
            keyed = context[["game_id", "play_id"]].assign(split_value=labels)
            classified = credits.merge(keyed, on=["game_id", "play_id"], validate="many_to_one")
            replay = classified.dropna(subset=["gsis_player_id", "split_value"]).groupby(["gsis_player_id", "split_value"])[list(COUNT_FIELDS)].sum()
            replay.index.names = ["player_id", "split_value"]
            official = read_export_csv(root, manifest, f"{dim}-{year}.csv", season=year).dropna(subset=["player_id"])
            a, b = official.set_index(["player_id", "split_value"])[list(COUNT_FIELDS)].align(replay, fill_value=0)
            assert a.eq(b).all().all(), (year, dim, "raw credit replay")
            stored = conn.execute(f"SELECT * FROM receiving_{dim}_preview WHERE season=?", [year]).df()
            view = proof["seasons"][str(year)][dim]
            assert all(view["coverage"]["checks"].values()) and view["production_matches_classified"]
            assert len(stored) == view["rows"]
            target = context.loc[context[["complete_pass", "incomplete_pass", "interception"]].eq(1).any(axis=1) & context.receiver_player_id.notna()].copy()
            target["split_value"] = labels.loc[target.index]
            target["positive"] = target.epa.gt(0).astype(int)
            grouped = target.groupby(["receiver_player_id", "split_value"]).agg(targets=("play_id", "size"), known_epa=("epa", "count"), mean_epa=("epa", "mean"), successes=("positive", "sum"), known_air=("air_yards", "count"), air=("air_yards", "sum"))
            grouped.index.names = ["player_id", "split_value"]
            aligned = stored.set_index(["player_id", "split_value"]).join(grouped)
            if targets_unavailable([year]):
                assert stored[["att", "epa", "success_pct"]].isna().all().all()
            else:
                valid = aligned.att.gt(0) & aligned.att.eq(aligned.targets) & aligned.att.eq(aligned.known_epa)
                assert aligned.success_pct.notna().eq(valid).all(), (year, dim, "success availability")
                # Compare the exact rational percentage. Multiplying a rounded
                # binary mean first can turn 63.75 into 63.74999999999999.
                expected_rate = pd.Series([_success_percent(row.successes, row.targets)
                    for row in aligned.loc[valid].itertuples()], index=aligned.index[valid], dtype=float)
                assert aligned.loc[valid].success_pct.eq(expected_rate).all(), (year, dim, "success rounding")
                known = aligned.epa.notna()
                assert aligned.loc[known].epa.eq(aligned.loc[known].mean_epa.round(4)).all()
            if air_yards_unavailable([year]):
                assert stored.air_yards.isna().all()
            else:
                valid = aligned.att.eq(aligned.targets.fillna(0)) & aligned.att.eq(aligned.known_air.fillna(0))
                assert aligned.air_yards.notna().eq(valid).all(), (year, dim, "air availability")
                assert aligned.loc[valid].air_yards.eq(aligned.loc[valid].air.fillna(0)).all()
            report["views"][dim] = {"rows": len(stored), "coverage": view["coverage"]["status"],
                                    "excluded_production": view["coverage"]["qualified_production"]["excluded"],
                                    "raw_credit_replay": True, "rates_and_air_verified": True}
        try:
            validate_snapshot(conn)
        except SnapshotValidationError as error:
            assert "not a publishable snapshot" in str(error)
            report["full_gate_rejects_preview"] = True
        else:
            raise AssertionError("Preview unexpectedly passed full gate")
    assert file_sha256(source) == baseline
    (root / "audit-result.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({key: value for key, value in report.items() if key != "views"}), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exports", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--rscript", type=Path, required=True)
    parser.add_argument("--r-library", type=Path, required=True)
    args = parser.parse_args()
    if not (args.exports / "audit/run.json").exists():
        auditor = Path(__file__).with_name("receiving_history_sources.R")
        subprocess.run([str(args.rscript.resolve()), "--vanilla", str(auditor),
                        str(args.exports.resolve()), str(args.r_library.resolve())], check=True)
    report = audit(args.exports, args.candidate, args.season, source=args.source)
    # A partial season can pass every available-data calculation and still must
    # not be mistaken for a complete-season success by a caller or CI.
    raise SystemExit(0 if report["full_game_coverage"] else 2)
