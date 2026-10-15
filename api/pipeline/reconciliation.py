"""Statistical identities shared by offline validation and the deploy test gate."""


def count_mismatches(conn, season, category, split_col, official_col, minimum):
    return conn.execute(f'''
        WITH s AS (
            SELECT player_id, SUM({split_col}) v FROM player_splits
            WHERE category = ? AND split_dim = 'down' AND season = ? GROUP BY 1),
        o AS (
            SELECT player_id, SUM({official_col}) v FROM weekly_player_stats
            WHERE season = ? AND season_type = 'REG' GROUP BY 1)
        SELECT COUNT(*) FROM o LEFT JOIN s USING (player_id)
        WHERE o.v >= ? AND COALESCE(s.v, 0) <> o.v
    ''', [category, season, season, minimum]).fetchone()[0]


def passing_epa_mismatches(conn, season):
    # New weekly feeds include no-down/two-point dropbacks in passing EPA.
    new_feed = 'sacks_suffered' in {r[0] for r in conn.execute('DESCRIBE weekly_player_stats').fetchall()}
    adjustment = 'COALESCE(two_pt.epa, 0)' if new_feed else '0'
    return conn.execute(f'''
        WITH sp AS (
            SELECT player_id, SUM(epa * att) epa, SUM(att) att FROM player_splits
            WHERE category = 'passing' AND split_dim = 'down' AND season = ? GROUP BY 1),
        two_pt AS (
            SELECT passer_player_id AS player_id, SUM(qb_epa) epa FROM plays
            WHERE season = ? AND season_type = 'REG' AND down IS NULL
              AND (pass_attempt = 1 OR COALESCE(sack, 0) = 1)
              AND passer_player_id IS NOT NULL GROUP BY 1),
        off AS (
            SELECT player_id, SUM(passing_epa) / NULLIF(SUM(attempts), 0) e
            FROM weekly_player_stats WHERE season = ? AND season_type = 'REG'
            GROUP BY 1 HAVING SUM(attempts) >= 100)
        SELECT COUNT(*) FROM off LEFT JOIN sp USING (player_id)
        LEFT JOIN two_pt USING (player_id)
        WHERE sp.att IS NULL OR sp.att = 0 OR sp.epa IS NULL OR off.e IS NULL
           OR NOT isfinite(off.e) OR NOT isfinite(sp.epa)
           OR ABS((sp.epa + {adjustment}) / NULLIF(sp.att, 0) - off.e) > 0.005
    ''', [season, season, season]).fetchone()[0]


def defensive_sack_mismatches(conn, season):
    import def_splits_builder
    eligible = def_splits_builder._events_union(int(season))
    return conn.execute(f'''
        WITH eligible AS (
            SELECT player_id FROM ({eligible}) GROUP BY player_id
            HAVING COUNT(*) >= {def_splits_builder._MIN_EVENTS}),
        ds AS (
            SELECT player_id, SUM(sacks) v FROM defense_splits
            WHERE split_dim = 'down' AND season = ? GROUP BY 1),
        raw AS (
            SELECT pid, SUM(w) v FROM (
                SELECT sack_player_id pid, 1.0 w FROM plays
                  WHERE season = ? AND season_type = 'REG' AND sack_player_id IS NOT NULL AND down IN (1,2,3,4)
                UNION ALL SELECT half_sack_1_player_id, 0.5 FROM plays
                  WHERE season = ? AND season_type = 'REG' AND half_sack_1_player_id IS NOT NULL AND down IN (1,2,3,4)
                UNION ALL SELECT half_sack_2_player_id, 0.5 FROM plays
                  WHERE season = ? AND season_type = 'REG' AND half_sack_2_player_id IS NOT NULL AND down IN (1,2,3,4)
            ) JOIN eligible ON eligible.player_id = pid GROUP BY pid)
        SELECT COUNT(*) FROM ds FULL OUTER JOIN raw ON ds.player_id = raw.pid
        WHERE GREATEST(COALESCE(ds.v, 0), COALESCE(raw.v, 0)) >= 5
          AND COALESCE(ds.v, 0) <> COALESCE(raw.v, 0)
    ''', [season] * 4).fetchone()[0]


def impossible_rates(conn):
    return conn.execute('''
        SELECT COUNT(*) FROM player_splits
        WHERE (success_pct IS NOT NULL AND
               (NOT isfinite(success_pct) OR success_pct < 0 OR success_pct > 100))
           OR (epa IS NOT NULL AND NOT isfinite(epa))
           OR att < 0 OR COALESCE(yards, 0) < -1000
    ''').fetchone()[0]


def season_checks(conn, season):
    """Mismatch counts and allowed counts; preserve established yardage tolerances."""
    checks = {}
    for name, category, column, official, minimum, allowed in (
        ('pass_attempts', 'passing', 'att', 'attempts', 100, 0),
        ('carries', 'rushing', 'att', 'carries', 50, 0),
        ('targets', 'receiving', 'att', 'targets', 40, 0),
        ('pass_yards', 'passing', 'yards', 'passing_yards', 1000, 0),
        ('rush_yards', 'rushing', 'yards', 'rushing_yards', 300, 2),
        ('rec_yards', 'receiving', 'yards', 'receiving_yards', 300, 6),
    ):
        checks[name] = (count_mismatches(conn, season, category, column, official, minimum), allowed)
    checks['passing_epa'] = (passing_epa_mismatches(conn, season), 0)
    checks['defensive_sacks'] = (defensive_sack_mismatches(conn, season), 0)
    return checks
