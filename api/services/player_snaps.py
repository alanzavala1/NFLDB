"""Player data functions; HTTP-independent selection and assembly."""
from database import query_to_dict
from sql_helpers import STAT_COLS, safe_query

OL_POSITIONS = {"C", "G", "T", "OT", "OG", "OL", "LS", "OC"}


def _pfr_identity(player_id: str) -> tuple[str | None, str | None]:
    """(pfr_id, player_name) for the snap_counts lookups below. Resolved in
    Python rather than a CTE: OR-ing the pfr and name paths into one WHERE
    kept DuckDB from using the snap_counts.pfr_player_id index."""
    rows = safe_query("""
        SELECT MAX(pfr_id) AS pfr_id, MAX(player_name) AS player_name
        FROM rosters WHERE player_id = ?
    """, [player_id])
    if not rows:
        return None, None
    return rows[0]["pfr_id"], rows[0]["player_name"]


def _get_snap_totals(player_id: str) -> dict:
    pfr_id, player_name = _pfr_identity(player_id)
    select = """
        SELECT sc.season,
            SUM(sc.offense_snaps)               AS offense_snaps,
            SUM(sc.defense_snaps)               AS defense_snaps,
            SUM(sc.st_snaps)                    AS st_snaps,
            ROUND(AVG(sc.offense_pct) * 100, 1) AS avg_offense_pct,
            ROUND(AVG(sc.defense_pct) * 100, 1) AS avg_defense_pct,
            ROUND(AVG(sc.st_pct) * 100, 1)      AS avg_st_pct
        FROM snap_counts sc
    """
    if pfr_id is not None:
        rows = safe_query(select + """
            WHERE sc.pfr_player_id = ?
            GROUP BY sc.season
        """, [pfr_id])
    elif player_name is not None:
        # No pfr id — match by name, constrained to season+team stints the
        # player actually had so common names don't cross-match.
        rows = safe_query(select + """
            WHERE LOWER(sc.player) = LOWER(?)
              AND EXISTS (
                  SELECT 1 FROM rosters r
                  WHERE r.player_id = ? AND r.season = sc.season AND r.team = sc.team
              )
            GROUP BY sc.season
        """, [player_name, player_id])
    else:
        rows = []
    return {r["season"]: r for r in rows}


def _get_snap_first_games(player_id: str, with_stats: bool = False) -> list[dict]:
    """
    Build game log using snap_counts as the authoritative appearance source.
    Team per game comes from snap_counts (correct for multi-team seasons and home/away).
    When with_stats=True, left-joins player_game_stats for real stats (K/P).
    When with_stats=False, all stat columns are 0 (OL).
    Uses player_all_teams to handle multi-team seasons in the name fallback.
    """
    if with_stats:
        stat_sel = ", ".join(f"COALESCE(pgs.{c}, 0.0) AS {c}" for c in STAT_COLS)
        pgs_join = "LEFT JOIN player_game_stats pgs ON pgs.game_id = ps.game_id AND pgs.player_id = ?"
        pgs_param = [player_id]
    else:
        stat_sel = ", ".join(f"0.0 AS {c}" for c in STAT_COLS)
        pgs_join = ""
        pgs_param = []

    # Same pfr-vs-name branching as _get_snap_totals (and same reason).
    pfr_id, player_name = _pfr_identity(player_id)
    if pfr_id is not None:
        snaps_where = "sc.pfr_player_id = ?"
        snaps_params = [pfr_id]
    elif player_name is not None:
        snaps_where = """LOWER(sc.player) = LOWER(?)
              AND EXISTS (
                  SELECT 1 FROM rosters r2
                  WHERE r2.player_id = ? AND r2.season = sc.season AND r2.team = sc.team
              )"""
        snaps_params = [player_name, player_id]
    else:
        return []

    return query_to_dict(f"""
        WITH player_roster AS (
            SELECT season, team, position, jersey_number, headshot_url
            FROM rosters WHERE player_id = ?
            QUALIFY ROW_NUMBER() OVER (PARTITION BY player_id, season ORDER BY season DESC) = 1
        ),
        player_snaps AS (
            SELECT sc.game_id, sc.season, sc.team
            FROM snap_counts sc
            WHERE {snaps_where}
        )
        SELECT
            s.game_id, ps.season, s.week, ps.team,
            CASE WHEN ps.team = s.home_team THEN s.away_team ELSE s.home_team END AS opponent,
            CASE WHEN ps.team = s.home_team THEN 'home' ELSE 'away' END           AS location,
            s.gameday, s.away_score, s.home_score,
            CASE
                WHEN s.away_score IS NULL                                    THEN NULL
                WHEN ps.team = s.home_team AND s.home_score > s.away_score   THEN 'W'
                WHEN ps.team = s.away_team AND s.away_score > s.home_score   THEN 'W'
                WHEN s.home_score = s.away_score                             THEN 'T'
                ELSE 'L'
            END AS result,
            s.game_type,
            {stat_sel},
            pr.position, pr.jersey_number, pr.headshot_url
        FROM player_snaps ps
        JOIN schedules s ON ps.game_id = s.game_id
        {pgs_join}
        LEFT JOIN player_roster pr ON pr.season = ps.season
        ORDER BY ps.season, s.week
    """, [player_id] + snaps_params + pgs_param)
