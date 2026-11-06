"""Receiving-credit pilot using only an in-memory database.

Inputs are provider play context and individual stat credits. This does not
download data, persist tables, apply split admission, or allocate EPA/air yards.
`target_credits` means observed stat-115 records, not verified target coverage.
"""
from typing import Literal

import duckdb
import pandas as pd


METRICS = ('target_credits', 'receptions', 'receiving_yards', 'receiving_tds')
_CONTEXT = ('game_id', 'play_id', 'season', 'season_type', 'down', 'qtr', 'two_point_attempt')
_CREDITS = ('game_id', 'play_id', 'gsis_player_id', 'stat_id', 'yards')


def _require_columns(frame: pd.DataFrame, columns, name: str) -> None:
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f'{name}: missing columns {sorted(missing)}')


def receiving_player_plays(plays: pd.DataFrame, credits: pd.DataFrame) -> pd.DataFrame:
    """One identified player/play row, preserving repeated and negative credits.

    Keep only ordinary regular-season receiving credits for the supplied plays.
    Unidentified players are excluded, matching the existing weekly loader.
    Credits outside the supplied play context are outside this query's scope.
    Duplicate regular-season play keys fail instead of multiplying statistics.
    """
    _require_columns(plays, _CONTEXT, 'plays')
    _require_columns(credits, _CREDITS, 'credits')
    with duckdb.connect(':memory:') as conn:
        conn.register('play_input', plays[list(_CONTEXT)])
        conn.register('credit_input', credits[list(_CREDITS)])
        invalid_context = conn.execute('''
            SELECT COUNT(*) FROM (
                SELECT game_id, play_id FROM play_input WHERE season_type = 'REG'
                GROUP BY game_id, play_id
                HAVING game_id IS NULL OR play_id IS NULL OR COUNT(*) <> 1
                    OR COUNT(season) <> 1
            )
        ''').fetchone()[0]
        if invalid_context:
            raise ValueError('plays: duplicate or missing regular-season play identity/season')
        conn.execute('''CREATE TEMP VIEW context AS
            SELECT game_id, play_id, season, down, qtr FROM play_input
            WHERE season_type = 'REG' AND COALESCE(two_point_attempt, 0) = 0''')
        invalid_yards = conn.execute('''SELECT COUNT(*) FROM credit_input
            JOIN context USING (game_id, play_id)
            WHERE gsis_player_id IS NOT NULL AND stat_id BETWEEN 21 AND 24
                AND (yards IS NULL OR NOT isfinite(yards))''').fetchone()[0]
        if invalid_yards:
            raise ValueError('credits: missing or nonfinite receiving yardage')
        return conn.execute('''
            WITH individual AS (
                SELECT game_id, play_id, gsis_player_id AS player_id,
                    COUNT(*) FILTER (WHERE stat_id = 115) AS target_credits,
                    COUNT(*) FILTER (WHERE stat_id IN (21,22)) AS receptions,
                    COALESCE(SUM(yards) FILTER (WHERE stat_id BETWEEN 21 AND 24), 0) AS receiving_yards,
                    COUNT(*) FILTER (WHERE stat_id IN (22,24)) AS receiving_tds
                FROM credit_input
                WHERE gsis_player_id IS NOT NULL AND (stat_id BETWEEN 21 AND 24 OR stat_id = 115)
                GROUP BY game_id, play_id, gsis_player_id
            )
            SELECT c.game_id, c.play_id, c.season, i.player_id, c.down, c.qtr,
                i.target_credits, i.receptions, i.receiving_yards, i.receiving_tds
            FROM individual i JOIN context c USING (game_id, play_id)
            ORDER BY c.season, c.game_id, c.play_id, i.player_id
        ''').df()


def receiving_splits(player_plays: pd.DataFrame, dimension: Literal['down', 'quarter']) -> pd.DataFrame:
    """Group credited counts/yardage by safe play context, before admission.

    Null/invalid downs and missing quarters are outside their respective splits.
    No target-depth, EPA or rate semantics are inferred for lateral recipients.
    """
    if dimension not in ('down', 'quarter'):
        raise ValueError('dimension must be down or quarter')
    _require_columns(player_plays, ('season', 'player_id', 'down', 'qtr', *METRICS), 'player_plays')
    if dimension == 'down':
        value = 'CAST(CAST(down AS INTEGER) AS VARCHAR)'
        order = 'CAST(down AS INTEGER)'
        condition = 'down IN (1,2,3,4)'
    else:
        value = "CASE WHEN qtr > 4 THEN 'OT' ELSE CAST(CAST(qtr AS INTEGER) AS VARCHAR) END"
        order = 'CASE WHEN qtr > 4 THEN 5 ELSE CAST(qtr AS INTEGER) END'
        condition = 'qtr IS NOT NULL'
    totals = ', '.join(f'SUM({metric}) AS {metric}' for metric in METRICS)
    with duckdb.connect(':memory:') as conn:
        conn.register('player_plays', player_plays)
        return conn.execute(f'''
            SELECT season, player_id, '{dimension}' AS split_dim,
                {value} AS split_value, {order} AS sort_order, {totals}
            FROM player_plays WHERE {condition}
            GROUP BY season, player_id, split_value, sort_order
            ORDER BY season, player_id, sort_order
        ''').df()
