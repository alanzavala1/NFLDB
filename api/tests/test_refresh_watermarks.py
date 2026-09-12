"""The refresh gate: does `check` notice when upstream moves?

This is the logic that decides whether the nightly job rebuilds anything, and
it had no test when it was watching a single asset — which is how it came to
report "nothing to do" for a day while snap counts for an already-ingested game
sat unpulled upstream.

Everything here stubs `remote_watermarks`, so no network and no database.
"""
import json

import pytest

from jobs import refresh


SEASON = 2026
PBP = "2026-09-11T04:00:00Z"
SNAPS = "2026-09-11T06:30:00Z"


def _remote(**overrides):
    """Upstream stamps with every watched asset published, unless overridden."""
    base = {key: PBP for key, _, _ in refresh.WATCHED_ASSETS}
    base.update(overrides)
    return base


def _marks(**overrides):
    """Local watermarks recording a complete ingest of the same stamps."""
    base = {f"{key}:{SEASON}": PBP for key, _, _ in refresh.WATCHED_ASSETS}
    base.update({f"{k}:{SEASON}": v for k, v in overrides.items()})
    return base


@pytest.fixture
def gate(tmp_path, monkeypatch, capsys):
    """Run `check` against stubbed upstream stamps and report its decision."""
    monkeypatch.delenv("REFRESH_FORCE", raising=False)
    monkeypatch.setenv("REFRESH_SEASON", str(SEASON))

    def run(remote: dict, marks: dict | None = None) -> tuple[bool, str]:
        path = tmp_path / "watermarks.json"
        if marks is not None:
            path.write_text(json.dumps(marks), encoding="utf-8")
        monkeypatch.setattr(refresh, "remote_watermarks", lambda season: remote)
        assert refresh.cmd_check(str(path)) == 0
        out = capsys.readouterr().out
        return ("CHANGED:" in out), out

    return run


class TestTheGate:
    def test_nothing_moved_means_no_rebuild(self, gate):
        changed, out = gate(_remote(), _marks())
        assert not changed
        assert "every watched asset unchanged" in out

    def test_snap_counts_alone_triggers_a_rebuild(self, gate):
        """The bug. Play-by-play is unchanged and used to be the only vote."""
        changed, out = gate(_remote(snaps=SNAPS), _marks())
        assert changed
        assert "snaps" in out

    def test_every_watched_asset_gets_a_vote(self, gate):
        for key, _, _ in refresh.WATCHED_ASSETS:
            changed, out = gate(_remote(**{key: "2026-12-25T00:00:00Z"}), _marks())
            assert changed, f"{key} moving upstream did not trigger a refresh"
            assert key in out

    def test_first_ever_run_rebuilds(self, gate):
        changed, _ = gate(_remote(), None)
        assert changed

    def test_an_unpublished_asset_is_not_a_change(self, gate):
        """A season with no NGS yet must not rebuild nightly forever."""
        changed, out = gate(_remote(ngs_passing=None, ngs_rushing=None), _marks())
        assert not changed
        assert "not published yet" in out

    def test_no_plays_upstream_loads_schedules_once(self, gate):
        remote = {key: None for key, _, _ in refresh.WATCHED_ASSETS}
        changed, _ = gate(remote, None)
        assert changed, "a season with no plays still needs its schedule"

        changed, out = gate(remote, {f"pbp:{SEASON}": refresh.SCHEDULES_ONLY})
        assert not changed
        assert "schedules already loaded" in out

    def test_force_overrides_everything(self, gate, monkeypatch):
        monkeypatch.setenv("REFRESH_FORCE", "1")
        changed, out = gate(_remote(), _marks())
        assert changed
        assert "forced" in out


class TestMovedHelper:
    def test_unpublished_upstream_never_counts(self):
        assert refresh._moved({}, SEASON, {"pbp": None}) == []

    def test_a_new_stamp_counts(self):
        assert refresh._moved({}, SEASON, {"pbp": PBP}) == ["pbp"]

    def test_the_same_stamp_does_not(self):
        assert refresh._moved({f"pbp:{SEASON}": PBP}, SEASON, {"pbp": PBP}) == []

    def test_watermarks_are_per_season(self):
        """A 2025 stamp must not satisfy 2026."""
        assert refresh._moved({"pbp:2025": PBP}, SEASON, {"pbp": PBP}) == ["pbp"]
