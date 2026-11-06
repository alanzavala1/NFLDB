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
from pipeline.source_results import SourceOutcome
from pipeline.vendor_sources import WATCHED_VENDOR_SOURCES


SEASON = 2026
PBP = "2026-09-11T04:00:00Z"
SNAPS = "2026-09-11T06:30:00Z"


@pytest.fixture(autouse=True)
def offline_writer_mode(monkeypatch):
    monkeypatch.setenv('NFL_DB_READ_ONLY', '0')


def test_failed_required_feed_never_advances_watermarks(tmp_path, monkeypatch):
    import database
    import ingest
    from pipeline.sources import SourceError

    path = tmp_path / 'watermarks.json'
    before = {f'pbp:{SEASON}': 'old-stamp'}
    path.write_text(json.dumps(before), encoding='utf-8')
    monkeypatch.setenv('REFRESH_SEASON', str(SEASON))
    monkeypatch.setattr(refresh, 'remote_watermarks', lambda season: _remote())
    monkeypatch.setattr(database, 'get_connection', lambda: object())

    def fail(*args, **kwargs):
        raise SourceError('weekly_player_stats', SEASON, 'download failed (TimeoutError)')

    monkeypatch.setattr(ingest, 'run_ingest', fail)
    with pytest.raises(SourceError, match='TimeoutError'):
        refresh.cmd_ingest(str(path))
    assert json.loads(path.read_text(encoding='utf-8')) == before


@pytest.mark.parametrize('status', ['loaded', 'empty', 'failed', 'not_found', 'unsupported'])
def test_vendor_watermarks_follow_observed_outcomes(tmp_path, monkeypatch, status):
    import database
    import ingest

    path = tmp_path / 'watermarks.json'
    before = _marks()
    path.write_text(json.dumps(before), encoding='utf-8')
    monkeypatch.setenv('REFRESH_SEASON', str(SEASON))
    monkeypatch.setattr(refresh, 'remote_watermarks',
                        lambda season: _remote(snaps=SNAPS, pfr_pass='unobserved-new'))
    monkeypatch.setattr(database, 'get_connection', lambda: object())
    monkeypatch.setattr(ingest, 'run_ingest', lambda *a, **k: [SourceOutcome('snap_counts', SEASON, status)])
    assert refresh.cmd_ingest(str(path)) == 0
    marks = json.loads(path.read_text(encoding='utf-8'))
    assert marks[f'snaps:{SEASON}'] == (SNAPS if status in ('loaded', 'empty') else before[f'snaps:{SEASON}'])
    # No outcome means no evidence that this other watched vendor was read.
    assert marks[f'pfr_pass:{SEASON}'] == before[f'pfr_pass:{SEASON}']


@pytest.mark.parametrize('status', ['loaded', 'not_found'])
def test_core_stamps_require_download_evidence_even_if_remote_asset_exists(tmp_path, monkeypatch, status):
    import database
    import ingest

    path = tmp_path / 'watermarks.json'
    before = {f'pbp:{SEASON}': 'old-play', f'weekly:{SEASON}': 'old-weekly'}
    path.write_text(json.dumps(before), encoding='utf-8')
    monkeypatch.setenv('REFRESH_SEASON', str(SEASON))
    monkeypatch.setattr(refresh, 'remote_watermarks', lambda season: _remote())
    monkeypatch.setattr(database, 'get_connection', lambda: object())
    outcomes = [SourceOutcome('plays', SEASON, status), SourceOutcome('weekly_player_stats', SEASON, status)]
    monkeypatch.setattr(ingest, 'run_ingest', lambda *a, **k: outcomes)
    refresh.cmd_ingest(str(path))
    marks = json.loads(path.read_text(encoding='utf-8'))
    assert marks[f'pbp:{SEASON}'] == (PBP if status == 'loaded' else 'old-play')
    assert marks[f'weekly:{SEASON}'] == (PBP if status == 'loaded' else 'old-weekly')


def test_schedules_only_stamp_requires_observed_schedule_rows(tmp_path, monkeypatch):
    import database
    import ingest

    path = tmp_path / 'watermarks.json'
    monkeypatch.setenv('REFRESH_SEASON', str(SEASON))
    monkeypatch.setattr(refresh, 'remote_watermarks',
                        lambda season: {key: None for key, _, _ in refresh.WATCHED_ASSETS})
    monkeypatch.setattr(database, 'get_connection', lambda: object())
    monkeypatch.setattr(ingest, 'run_ingest', lambda *a, **k: [])
    refresh.cmd_ingest(str(path))
    assert json.loads(path.read_text(encoding='utf-8')) == {}
    monkeypatch.setattr(ingest, 'run_ingest',
                        lambda *a, **k: [SourceOutcome('schedules', SEASON, 'loaded', 1)])
    refresh.cmd_ingest(str(path))
    assert json.loads(path.read_text(encoding='utf-8')) == {f'pbp:{SEASON}': refresh.SCHEDULES_ONLY}


def test_watch_catalog_matches_the_assets_the_adapters_fetch():
    watched = {key: (tag, asset) for key, tag, asset in refresh.WATCHED_ASSETS}
    for key, spec in WATCHED_VENDOR_SOURCES.items():
        assert watched[key] == (spec.release, spec.asset)


def test_remote_gate_skips_assets_outside_declared_coverage(monkeypatch):
    def releases(tag):
        assert tag in ('pbp', 'stats_player'), 'unsupported vendor must not be fetched'
        return {}

    monkeypatch.setattr(refresh, '_release_assets', releases)
    remote = refresh.remote_watermarks(1999)
    assert all(remote[key] is None for key in WATCHED_VENDOR_SOURCES)


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
