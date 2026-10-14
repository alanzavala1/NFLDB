"""Core seasonal feed downloads, independent of database storage.

Only an actual upstream HTTP 404 is a missing asset. Other failures stop the
refresh; an empty published file is not evidence of an unplayed season.
"""
from dataclasses import dataclass
from urllib.error import HTTPError

import pandas as pd


# nflfastR play-by-play ships ~396 columns; the app uses ~169. Storing only
# these keeps the DuckDB file ~half the size with no loss of functionality
# (verified: every builder + runtime query runs against this subset). Anything
# not present in a given season's download is simply skipped.
PLAYS_KEEP_COLUMNS = [
    'play_id', 'game_id', 'home_team', 'away_team', 'season_type', 'week',
    'posteam', 'posteam_type', 'defteam', 'yardline_100', 'game_seconds_remaining', 'drive',
    'sp', 'qtr', 'down', 'ydstogo', 'time', 'desc', 'play_type',
    'yards_gained', 'shotgun', 'no_huddle', 'qb_kneel', 'qb_spike', 'pass_length',
    'pass_location', 'air_yards', 'yards_after_catch', 'run_location', 'run_gap', 'field_goal_result',
    'kick_distance', 'extra_point_result', 'two_point_conv_result', 'timeout', 'td_team', 'td_player_id',
    'total_home_score', 'total_away_score', 'posteam_score', 'defteam_score', 'score_differential', 'epa',
    'wp', 'home_wp', 'wpa', 'air_wpa', 'yac_wpa', 'punt_blocked',
    'first_down_rush', 'first_down_pass', 'third_down_converted', 'third_down_failed', 'fourth_down_converted', 'fourth_down_failed',
    'incomplete_pass', 'touchback', 'interception', 'punt_inside_twenty', 'safety', 'penalty',
    'fumble_lost', 'qb_hit', 'rush_attempt', 'pass_attempt', 'sack', 'touchdown',
    'pass_touchdown', 'rush_touchdown', 'return_touchdown', 'extra_point_attempt', 'two_point_attempt', 'field_goal_attempt',
    'punt_attempt', 'fumble', 'complete_pass', 'passer_player_id', 'passer_player_name', 'passing_yards',
    'receiver_player_id', 'receiver_player_name', 'receiving_yards', 'rusher_player_id', 'rusher_player_name', 'rushing_yards',
    'interception_player_id', 'interception_player_name', 'punt_returner_player_id', 'punt_returner_player_name', 'punter_player_id', 'punter_player_name',
    'kicker_player_name', 'kicker_player_id', 'tackle_for_loss_1_player_id', 'tackle_for_loss_1_player_name', 'tackle_for_loss_2_player_id', 'tackle_for_loss_2_player_name',
    'qb_hit_1_player_id', 'qb_hit_1_player_name', 'qb_hit_2_player_id', 'qb_hit_2_player_name', 'forced_fumble_player_1_player_id', 'forced_fumble_player_1_player_name',
    'forced_fumble_player_2_player_id', 'forced_fumble_player_2_player_name', 'solo_tackle_1_player_id', 'solo_tackle_2_player_id', 'solo_tackle_1_player_name', 'solo_tackle_2_player_name',
    'assist_tackle_1_player_id', 'assist_tackle_1_player_name', 'assist_tackle_2_player_id', 'assist_tackle_2_player_name', 'assist_tackle_3_player_id', 'assist_tackle_3_player_name',
    'assist_tackle_4_player_id', 'assist_tackle_4_player_name', 'pass_defense_1_player_id', 'pass_defense_1_player_name', 'pass_defense_2_player_id', 'pass_defense_2_player_name',
    'fumble_recovery_1_team', 'fumble_recovery_1_player_id', 'fumble_recovery_1_player_name', 'fumble_recovery_2_team', 'fumble_recovery_2_player_id', 'fumble_recovery_2_player_name',
    'sack_player_id', 'sack_player_name', 'half_sack_1_player_id', 'half_sack_1_player_name', 'half_sack_2_player_id', 'half_sack_2_player_name',
    'return_yards', 'penalty_team', 'penalty_player_id', 'penalty_yards', 'penalty_type', 'season',
    'cpoe', 'stadium', 'away_score', 'home_score', 'location', 'result',
    'total', 'spread_line', 'total_line', 'div_game', 'roof', 'surface',
    'temp', 'wind', 'success', 'passer', 'rusher', 'receiver',
    'pass', 'rush', 'first_down', 'special', 'play', 'name',
    'jersey_number', 'id', 'qb_epa', 'xpass', 'pass_oe', 'nflverse_game_id',
    'route',
]


# Listed in PLAYS_KEEP_COLUMNS but never present in the pbp parquet itself —
# they arrive from other nflverse feeds (FTN charting, the game-id map) and are
# joined in later. Parquet rejects the whole column list if one name is absent,
# so these are dropped from the request; the post-fetch prune below still keeps
# whatever did arrive.
PBP_COLUMNS_FROM_OTHER_FEEDS = ("route", "nflverse_game_id")


# nflverse retired the per-season `player_stats_{year}.parquet` assets after 2024
# and moved weekly stats to the `stats_player` release. nfl_data_py still asks
# for the old path, so `import_weekly_data` returned nothing from 2025 on. That
# surfaced as a swallowed exception, an empty frame, and a silent fall back to
# deriving offensive stats from play-by-play — for exactly the seasons people
# are looking at. The fallback miscounts two-point conversion passes as passing
# touchdowns: 12 quarterbacks were over-credited, +16 league-wide, in 2025.
WEEKLY_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "stats_player/stats_player_week_{season}.parquet"
)

# Keys the offensive build joins and groups on, plus season_type, which the
# splits and the reconciliation gate filter to REG.
WEEKLY_KEY_COLUMNS = ("player_id", "season", "week", "season_type", "team")

# Every stat column build_offensive_stats_from_weekly reads, exhaustively. Each
# name here is interpolated straight into that SELECT, so a name MISSING from
# this list is a column that can vanish upstream without anything failing. Five
# were missing — the three EPA columns, air yards and YAC — which is exactly the
# set that could have turned into a silent 0.00 on every page that shows them.
# test_weekly_columns.py pins the two lists to each other so they cannot drift
# apart again.
WEEKLY_STAT_COLUMNS = (
    "completions", "attempts", "passing_yards", "passing_tds",
    "passing_interceptions", "sacks_suffered", "passing_epa",
    "targets", "receptions", "receiving_yards", "receiving_tds",
    "receiving_air_yards", "receiving_yards_after_catch", "receiving_epa",
    "carries", "rushing_yards", "rushing_tds", "rushing_epa",
)

# Checked twice: against the downloaded frame when ingesting, and against the
# stored table when reading. Absence is a migration, not a gap.
WEEKLY_REQUIRED_COLUMNS = WEEKLY_KEY_COLUMNS + WEEKLY_STAT_COLUMNS

PBP_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "pbp/play_by_play_{season}.parquet"
)


class SourceError(RuntimeError):
    """A feed failed or cannot supply data required by this refresh."""

    def __init__(self, source: str, season: int, reason: str):
        self.source = source
        self.season = season
        super().__init__(f'{source}[{season}]: {reason}')


@dataclass
class SeasonalFeed:
    data: pd.DataFrame | None
    loaded_seasons: list[int]
    not_found_seasons: list[int]


def _read_parquet(source: str, season: int, url: str, *, columns=None, log=print):
    """Read a seasonal asset; only known projection drift permits a full retry."""
    try:
        if columns is None:
            frame = pd.read_parquet(url)
        else:
            try:
                frame = pd.read_parquet(url, columns=columns)
            except ValueError as error:
                # fastparquet is the engine in uv.lock. Historical files may
                # predate requested columns; other ValueErrors are real faults.
                if not str(error).startswith(
                    'Following columns were requested but are not available:'
                ):
                    raise
                log(f'  {source}[{season}]: older schema; reading available columns')
                frame = pd.read_parquet(url)
    except HTTPError as error:
        if error.code == 404:
            log(f'  {source}[{season}]: asset not found (HTTP 404)')
            return None
        raise SourceError(source, season, f'download failed (HTTP {error.code})') from error
    except Exception as error:
        raise SourceError(source, season, f'download failed ({type(error).__name__})') from error
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise SourceError(source, season, 'published asset returned no rows')
    return frame


def fetch_play_by_play(seasons: list[int], log=print) -> SeasonalFeed:
    """Fetch each season independently and retain the provider's float32 policy.

    Reading parquet directly avoids nfl_data_py's broken exception handler,
    which masks the original download error with NameError. Its season labeling,
    float downcast and the existing app column projection are preserved here.
    """
    frames, loaded, missing = [], [], []
    columns = [c for c in PLAYS_KEEP_COLUMNS
               if c not in (*PBP_COLUMNS_FROM_OTHER_FEEDS, 'season')]
    for season in dict.fromkeys(seasons):
        frame = _read_parquet('plays', season, PBP_URL.format(season=season),
                              columns=columns, log=log)
        if frame is None:
            missing.append(season)
            continue
        absent = [c for c in ('game_id', 'play_id', 'week') if c not in frame.columns]
        if absent:
            raise SourceError('plays', season, f'feed is missing required columns {absent}')
        frame = frame.copy()
        frame['season'] = season
        frame = frame[[c for c in PLAYS_KEEP_COLUMNS if c in frame.columns]]
        frames.append(frame)
        loaded.append(season)
    data = pd.concat(frames, ignore_index=True) if frames else None
    if data is not None:
        floats = data.select_dtypes(include=['float64']).columns
        data[floats] = data[floats].astype('float32')
    return SeasonalFeed(data, loaded, missing)


def fetch_weekly_stats(seasons: list[int], log=print) -> SeasonalFeed:
    """Validate each official weekly asset before frames can mask schema drift."""
    frames, loaded, missing = [], [], []
    for season in dict.fromkeys(seasons):
        frame = _read_parquet('weekly_player_stats', season,
                              WEEKLY_STATS_URL.format(season=season), log=log)
        if frame is None:
            missing.append(season)
            continue
        absent = [c for c in WEEKLY_REQUIRED_COLUMNS if c not in frame.columns]
        if absent:
            raise SourceError('weekly_player_stats', season,
                              f'feed is missing required columns {absent}')
        if frame['season'].isna().any() or not frame['season'].eq(season).all():
            raise SourceError('weekly_player_stats', season, 'asset contains unexpected seasons')
        frames.append(frame)
        loaded.append(season)
    return SeasonalFeed(pd.concat(frames, ignore_index=True) if frames else None,
                        loaded, missing)
