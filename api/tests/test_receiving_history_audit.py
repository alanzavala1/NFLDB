"""Independent audit must retain source gaps and reject changed evidence."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pandas as pd
import pytest

from experiments.receiving_history_audit import audit, _success_percent
from pipeline import receiving_preview as preview
from tests.test_receiving_preview import source, fake_export


@pytest.fixture
def completed_audit(source, tmp_path, fake_export):
    candidate, exports = tmp_path / "candidate.duckdb", tmp_path / "exports"
    preview.prepare_receiving_preview(source, candidate, exports, [2024],
                                      rscript=Path(sys.executable), library=tmp_path)
    context = pd.read_csv(exports / "context-2024.csv")
    root = exports / "audit"
    root.mkdir()
    context.to_csv(root / "context-2024.csv", index=False)
    pd.DataFrame([dict(player_id="receiver", qualifying_plays=28)]).to_csv(root / "qualified-2024.csv", index=False)
    credits = []
    for row in context.itertuples():
        yac = 8 if row.play_id in (2, 3, 24, 25) else 7
        for stat, yards in ((21, 10), (115, 0), (111, 2), (113, yac), (4, 0)):
            credits.append(dict(game_id=row.game_id, play_id=row.play_id, team_abbr="BUF",
                                gsis_player_id="receiver", stat_id=stat, yards=yards))
    pd.DataFrame(credits).to_csv(root / "credits-2024.csv", index=False)
    pd.DataFrame([dict(game_id="game", season=2024, game_type="REG", gameday="2024-09-08",
                       home_score=14, away_score=7)]).to_csv(root / "schedules-2024.csv", index=False)
    bind_audit(exports)
    return source, candidate, exports


def bind_audit(exports):
    root = exports / "audit"
    files = {p.name: preview.file_sha256(p) for p in root.iterdir() if p.name != "run.json"}
    (root / "run.json").write_text(json.dumps({
        "source_manifest_sha256": preview.file_sha256(exports / "run.json"), "files": files}))


def test_complete_fixture_passes_every_view_and_supports_quoted_source_paths(completed_audit, tmp_path):
    source, candidate, exports = completed_audit
    quoted = tmp_path / "source's snapshot.duckdb"
    shutil.copyfile(source, quoted)
    report = audit(exports, candidate, 2024, source=quoted)
    assert report["status"] == "passed" and report["full_game_coverage"]
    assert report["qualified_players"] == 1
    assert len(report["views"]) == 17
    assert all(view["raw_credit_replay"] for view in report["views"].values())
    assert report["full_gate_rejects_preview"]


def test_missing_game_keeps_verified_counts_but_cli_fails_completeness(completed_audit, tmp_path):
    source, candidate, exports = completed_audit
    schedule = exports / "audit/schedules-2024.csv"
    games = pd.read_csv(schedule)
    pd.concat([games, games.assign(game_id="missing_game")]).to_csv(schedule, index=False)
    bind_audit(exports)
    report = audit(exports, candidate, 2024, source=source)
    assert report["status"] == "source_gap" and not report["full_game_coverage"]
    assert report["missing_game_ids"] == ["missing_game"]
    assert report["views"]["down"]["rows"] == 4
    command = [sys.executable, "-m", "experiments.receiving_history_audit", "--exports", str(exports),
               "--candidate", str(candidate), "--source", str(source), "--season", "2024",
               "--rscript", sys.executable, "--r-library", str(tmp_path)]
    assert subprocess.run(command, capture_output=True).returncode == 2


@pytest.mark.parametrize("fault", ["bytes", "game_scope", "raw_credit", "qualification"])
def test_changed_or_self_consistent_wrong_evidence_cannot_pass(completed_audit, fault):
    source, candidate, exports = completed_audit
    root = exports / "audit"
    if fault == "bytes":
        path = root / "context-2024.csv"
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        name = {"game_scope": "context", "raw_credit": "credits", "qualification": "qualified"}[fault]
        path = root / f"{name}-2024.csv"
        frame = pd.read_csv(path)
        if fault == "game_scope":
            frame.loc[0, "game_id"] = "different_game"
        elif fault == "raw_credit":
            frame.loc[0, "yards"] += 1
        else:
            frame.loc[0, "qualifying_plays"] += 1
        frame.to_csv(path, index=False)
        bind_audit(exports)
    with pytest.raises(AssertionError):
        audit(exports, candidate, 2024, source=source)


def test_independent_rounding_uses_exact_counts_for_known_2002_case():
    assert round(100 * (51 / 80), 1) == 63.7
    assert _success_percent(51, 80) == 63.8
    assert _success_percent(49, 80) == 61.2


def test_optimized_python_cannot_silently_disable_validation():
    result = subprocess.run([sys.executable, "-O", "-m", "experiments.receiving_history_audit", "--help"],
                            capture_output=True, text=True)
    assert result.returncode != 0
    assert "without Python -O" in result.stderr
