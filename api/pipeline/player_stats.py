"""Compose reconciled player-game rows, independently of download orchestration."""
import pandas as pd

from config import era_team_case
from data_errors import is_missing_data_error
from pipeline.sources import WEEKLY_REQUIRED_COLUMNS
from pipeline.normalization import merge_all_stats, normalize_relocated_teams
from pipeline.play_stats import (
    DEFENSIVE_SLOTS, build_passing_stats, build_receiving_stats, build_rushing_stats,
    build_slot_stats, build_kicker_stats, build_punter_stats, build_returner_stats,
)
from pipeline.storage import store_player_game_stats


def build_offensive_stats_from_weekly(conn, seasons: list[int], log=print) -> pd.DataFrame:
    """
    Passing/rushing/receiving stats from nflverse official weekly player data.

    nflverse derives these from the same official NFL source PFR uses, so play
    classification edge cases (sack encoding, 2-pt conversions, pick-sixes) are
    handled correctly without any manual filtering on our end.
    """
    try:
        cols = {r[0] for r in conn.execute("DESCRIBE weekly_player_stats").fetchall()}
    except Exception as error:
        if not is_missing_data_error(error):
            raise
        return pd.DataFrame()

    # An absent table means "no official data, use the fallback", which is a
    # real state on a fresh database. A table that is PRESENT but missing
    # columns is a half-finished migration, and resolving those to zero would
    # publish wrong numbers under the official-data label — the exact failure
    # this module was just rewritten to stop. So it raises instead.
    absent = [c for c in WEEKLY_REQUIRED_COLUMNS if c not in cols]
    if absent:
        raise RuntimeError(
            f"weekly_player_stats is missing {absent}. If those are the "
            f"pre-stats_player names (recent_team / interceptions / sacks), "
            f"re-run the ingest: load_weekly_player_stats rebuilds the table "
            f"from the new feed. Otherwise nflverse has changed the schema "
            f"again — update WEEKLY_STAT_COLUMNS and the SELECT below together."
        )

    season_clause = ', '.join(str(s) for s in seasons)

    def col(name, alias):
        return f'COALESCE(w.{name}, 0) AS {alias}'

    # game_id is present in modern nflverse weekly data; fall back to schedule join if absent.
    # `team` (was `recent_team` before the stats_player rename) is the MODERN
    # franchise abbreviation while schedules use the era one, so match on the
    # era-mapped value — joining on it directly silently dropped
    # every pre-relocation OAK/SD/STL offensive row (the join found no game_id).
    if 'game_id' in cols:
        game_id_expr = 'w.game_id'
        join_clause  = ''
    else:
        era_team     = era_team_case('w.team', 'w.season')
        game_id_expr = 'sch.game_id'
        join_clause  = f"""
            LEFT JOIN schedules sch
                ON  sch.season = w.season AND sch.week = w.week
                AND (sch.home_team = {era_team} OR sch.away_team = {era_team})
        """

    name_col = 'player_display_name' if 'player_display_name' in cols else 'player_name'

    sql = f"""
        SELECT
            {game_id_expr}                                              AS game_id,
            w.player_id,
            w.{name_col}                                                AS player_name,
            w.team                                                      AS team,
            w.season,
            w.week,
            {col('completions',                 'completions')},
            {col('attempts',                    'attempts')},
            {col('passing_yards',               'pass_yards')},
            {col('passing_tds',                 'pass_tds')},
            {col('passing_interceptions',       'interceptions_thrown')},
            {col('sacks_suffered',              'sacks_taken')},
            {col('passing_epa',                 'pass_epa')},
            {col('targets',                     'targets')},
            {col('receptions',                  'receptions')},
            {col('receiving_yards',             'rec_yards')},
            {col('receiving_tds',               'rec_tds')},
            {col('receiving_air_yards',         'air_yards')},
            {col('receiving_yards_after_catch', 'yac')},
            {col('receiving_epa',               'rec_epa')},
            {col('carries',                     'carries')},
            {col('rushing_yards',               'rush_yards')},
            {col('rushing_tds',                 'rush_tds')},
            {col('rushing_epa',                 'rush_epa')}
        FROM weekly_player_stats w
        {join_clause}
        WHERE w.season IN ({season_clause})
        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY w.player_id, w.season, w.week
            ORDER BY COALESCE(w.attempts, 0) + COALESCE(w.carries, 0) + COALESCE(w.targets, 0) DESC
        ) = 1
    """

    df = conn.execute(sql).df()
    # Drop rows where the schedule join failed to resolve a game_id (old seasons without game_id column)
    df = df[df["game_id"].notna()]
    log(f"  offensive (weekly): {len(df):,} player-game rows")
    return df


def build_player_game_stats(conn, plays: pd.DataFrame, seasons: list[int], log=print) -> None:
    """Build player_game_stats for `seasons` from a plays frame + the weekly table.

    Factored out of run_ingest so a repair can rebuild seasons from plays
    already in the DB without re-downloading play-by-play.
    """
    available = set(plays.columns)
    log(f"\nBuilding player_game_stats for {seasons}...")

    # Offensive stats: prefer official nflverse weekly data (same source as PFR).
    # Falls back to play-by-play derivation if weekly data isn't available.
    offensive = build_offensive_stats_from_weekly(conn, seasons, log=log)
    if offensive.empty:
        # Loud, and specific about the cost: this path miscounts two-point
        # conversion passes as passing touchdowns. It is a degraded mode, not
        # an equivalent one.
        log("  WARNING: no official weekly stats for these seasons — deriving "
            "offensive stats from play-by-play instead. Passing touchdowns will "
            "be over-counted on two-point conversions.")
        offensive = merge_all_stats(
            build_passing_stats(conn, available, seasons),
            build_receiving_stats(conn, available, seasons),
            build_rushing_stats(conn, available, seasons),
        )

    defensive = build_slot_stats(plays, DEFENSIVE_SLOTS)
    kicker    = build_kicker_stats(plays)
    punter    = build_punter_stats(plays)
    returner  = build_returner_stats(plays)

    player_game_stats = merge_all_stats(offensive, defensive, kicker, punter, returner)

    # Drop any rows with no game_id (orphaned rows from failed joins)
    player_game_stats = player_game_stats[player_game_stats["game_id"].notna()]

    # pbp-derived frames carry modern franchise abbreviations; rewrite to era
    player_game_stats = normalize_relocated_teams(player_game_stats)

    # Deduplicate on (game_id, player_id) — keep the row with the most total activity
    stat_cols = [c for c in player_game_stats.columns if c not in ("game_id", "player_id", "season", "week", "team", "player_name")]
    if stat_cols:
        player_game_stats["_total"] = player_game_stats[stat_cols].fillna(0).sum(axis=1)
        player_game_stats = (
            player_game_stats
            .sort_values("_total", ascending=False)
            .drop_duplicates(subset=["game_id", "player_id"])
            .drop(columns=["_total"])
        )

    store_player_game_stats(conn, player_game_stats, seasons, log=log)
