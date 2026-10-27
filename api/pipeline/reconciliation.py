"""Statistical identities shared by offline validation and the deploy test gate."""
from splits_core import PASSING_EPA_PLAY


def receiving_total_checks(conn, season):
    """Preserve weekly receiving production in prepared player-game rows.

    Compare every identified player/week, without targets, split eligibility or
    minimum volume. Week keys also support weekly feeds without game_id. This
    checks transfer of source counts, not source completeness or target coverage.
    """
    metrics = (('receptions', 'receptions'), ('receiving_yards', 'rec_yards'),
               ('receiving_tds', 'rec_tds'))
    expected = ', '.join(f'SUM({source}) AS {stored}' for source, stored in metrics)
    prepared = ', '.join(f'SUM(p.{stored}) AS {stored}' for _, stored in metrics)
    comparisons = ', '.join(f'''COUNT(*) FILTER (WHERE
        COALESCE(w.{stored}, 0) <> COALESCE(p.{stored}, 0)
        OR NOT isfinite(COALESCE(w.{stored}, 0))
        OR NOT isfinite(COALESCE(p.{stored}, 0)))''' for _, stored in metrics)
    counts = conn.execute(f'''
        WITH w AS (
            SELECT player_id, week, {expected} FROM weekly_player_stats
            WHERE season = ? AND season_type = 'REG' AND player_id IS NOT NULL
            GROUP BY player_id, week),
        p AS (
            SELECT p.player_id, p.week, {prepared} FROM player_game_stats p
            JOIN schedules s ON s.game_id = p.game_id AND s.game_type = 'REG'
            WHERE p.season = ? GROUP BY p.player_id, p.week)
        SELECT {comparisons} FROM w FULL OUTER JOIN p USING (player_id, week)
    ''', [season, season]).fetchone()
    return {f'player_game_{source}': (count, 0)
            for (source, _), count in zip(metrics, counts)}


def count_mismatches(conn, season, category, split_col, official_col, minimum):
    import splits_builder

    # Official volume alone does not imply split admission (for example, a
    # receiver can gain 300 yards on fewer than 25 targets). Select eligibility
    # from source plays, not stored splits, so missing qualified output fails.
    available = {r[0] for r in conn.execute('DESCRIBE plays').fetchall()}
    eligibility = splits_builder.qualification_ctes(category, season, available)
    return conn.execute(f'''
        {eligibility}, s AS (
            SELECT player_id, SUM({split_col}) v FROM player_splits
            WHERE category = ? AND split_dim = 'down' AND season = ? GROUP BY 1),
        o AS (
            SELECT player_id, SUM({official_col}) v FROM weekly_player_stats
            WHERE season = ? AND season_type = 'REG' GROUP BY 1)
        SELECT COUNT(*) FROM o JOIN qualified USING (player_id)
        LEFT JOIN s USING (player_id)
        WHERE o.v >= ? AND (s.player_id IS NULL OR COALESCE(s.v, 0) <> o.v)
    ''', [category, season, season, minimum]).fetchone()[0]


def passing_epa_mismatches(conn, season):
    # New weekly feeds include no-down/two-point dropbacks in passing EPA.
    new_feed = 'sacks_suffered' in {r[0] for r in conn.execute('DESCRIBE weekly_player_stats').fetchall()}
    adjustment = 'COALESCE(two_pt.epa, 0)' if new_feed else '0'
    return conn.execute(f'''
        WITH sp AS (
            SELECT player_id, SUM(epa * att) epa, SUM(att) att,
                COUNT(*) FILTER (WHERE att IS NULL OR (att > 0 AND epa IS NULL)
                                 OR (att = 0 AND epa IS NOT NULL)) invalid
            FROM player_splits
            WHERE category = 'passing' AND split_dim = 'down' AND season = ? GROUP BY 1),
        sack_only AS (
            -- A sack-only down has NULL EPA/attempt, not zero EPA. Its raw
            -- numerator cannot be reconstructed by multiplying that rate by 0.
            SELECT p.passer_player_id AS player_id, SUM(p.qb_epa) epa
            FROM plays p JOIN player_splits s
              ON s.player_id = p.passer_player_id AND s.season = p.season
             AND s.category = 'passing' AND s.split_dim = 'down'
             AND TRY_CAST(s.split_value AS INTEGER) = p.down AND s.att = 0
            WHERE p.season = ? AND p.season_type = 'REG' AND {PASSING_EPA_PLAY}
            GROUP BY p.passer_player_id),
        two_pt AS (
            SELECT passer_player_id AS player_id, SUM(qb_epa) epa FROM plays
            WHERE season = ? AND season_type = 'REG' AND down IS NULL
              AND {PASSING_EPA_PLAY}
              AND passer_player_id IS NOT NULL GROUP BY 1),
        off AS (
            SELECT player_id, SUM(passing_epa) / NULLIF(SUM(attempts), 0) e
            FROM weekly_player_stats WHERE season = ? AND season_type = 'REG'
            GROUP BY 1 HAVING SUM(attempts) >= 100)
        SELECT COUNT(*) FROM off LEFT JOIN sp USING (player_id)
        LEFT JOIN two_pt USING (player_id)
        LEFT JOIN sack_only USING (player_id)
        WHERE sp.att IS NULL OR sp.att = 0 OR sp.epa IS NULL OR off.e IS NULL OR sp.invalid > 0
           OR NOT isfinite(off.e) OR NOT isfinite(sp.epa)
           OR ABS((sp.epa + COALESCE(sack_only.epa, 0) + {adjustment}) / NULLIF(sp.att, 0) - off.e) > 0.005
    ''', [season, season, season, season]).fetchone()[0]


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


def passing_source_epa_mismatches(conn, season):
    """Keep the weekly EPA identity after exact replay validates stored rates.

    A flagged split rate cannot reconstruct a whole numerator. Compare source
    pass/spike QB EPA (including conversions) against the captured weekly feed,
    with the existing 0.005 per-attempt tolerance. Stored metric values and NULL
    policies must already have passed exact source-bound passing replay.
    """
    return conn.execute(f'''
        WITH raw AS (SELECT passer_player_id AS player_id,SUM(qb_epa) AS epa
            FROM plays WHERE season=? AND season_type='REG' AND {PASSING_EPA_PLAY}
            GROUP BY passer_player_id),
        official AS (SELECT player_id,SUM(attempts) AS attempts,SUM(passing_epa) AS epa
            FROM weekly_player_stats WHERE season=? AND season_type='REG'
            GROUP BY player_id HAVING SUM(attempts)>=100)
        SELECT COUNT(*) FROM official o LEFT JOIN raw r USING(player_id)
        WHERE o.epa IS NULL OR r.epa IS NULL OR NOT isfinite(o.epa) OR NOT isfinite(r.epa)
           OR ABS((r.epa-o.epa)/o.attempts)>0.005
    ''', [season,season]).fetchone()[0]


def impossible_rates(conn):
    return conn.execute('''
        SELECT COUNT(*) FROM player_splits
        WHERE (success_pct IS NOT NULL AND
               (NOT isfinite(success_pct) OR success_pct < 0 OR success_pct > 100))
           OR (epa IS NOT NULL AND NOT isfinite(epa))
           OR att < 0 OR COALESCE(yards, 0) < -1000
    ''').fetchone()[0]


def season_checks(conn, season, *, official_receiving=False, official_passing=False):
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
        if (official_receiving and category == 'receiving') or (official_passing and category == 'passing'):
            # The caller must run source-bound receiving validation instead;
            # a Down subtotal is not an independent whole-season reference.
            continue
        checks[name] = (count_mismatches(conn, season, category, column, official, minimum), allowed)
    checks['passing_epa'] = ((passing_source_epa_mismatches if official_passing else passing_epa_mismatches)(conn, season), 0)
    checks['defensive_sacks'] = (defensive_sack_mismatches(conn, season), 0)
    return checks
