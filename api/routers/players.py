"""Player profile, advanced stats, and comparable-player endpoints."""
from fastapi import APIRouter, HTTPException, Query

from database import query_to_dict
from schemas.leaders import PlayerComparable
from schemas.players import PlayerProfile, PlayerSplit, DefensiveSplit
from sql_helpers import PGS_STAT_SEL, ROSTER_CTE, STAT_COLS, safe_query

router = APIRouter()


# OL/K/P players: use snap_counts as the authoritative game-appearance source so the team per
# game is always correct (pgs.team is the away-team slot and is wrong for home players;
# ROSTER_CTE picks one team per player+season arbitrarily for multi-team players).
_OL_POSITIONS = {"C", "G", "T", "OT", "OG", "OL", "LS", "OC"}
_SNAP_FIRST_POSITIONS = _OL_POSITIONS | {"K", "P"}


def _get_ngs(player_id: str, cpoe_fallback: dict | None = None) -> dict:
    """Aggregate NGS weekly data by season for a player.

    `cpoe_fallback` is {season: cpoe} derived from play-by-play (see
    _get_pbp_stats). NGS tracking starts at 2016 — without the fallback,
    pre-2016 QBs (Favre, Romo, Brees through 2015, etc.) would have an empty
    cell where every other QB has a value. The NGS value wins when present
    (tracking-based, more authoritative); plays-derived only fills the gaps.
    """
    result: dict[int, dict] = {}

    for row in safe_query("""
        SELECT season,
            ROUND(AVG(avg_time_to_throw), 2)                         AS avg_time_to_throw,
            ROUND(AVG(avg_intended_air_yards), 1)                     AS adot,
            ROUND(AVG(avg_completed_air_yards), 1)                    AS avg_completed_air_yards,
            ROUND(AVG(completion_percentage_above_expectation), 1)    AS cpoe,
            ROUND(AVG(aggressiveness), 1)                             AS aggressiveness,
            ROUND(AVG(expected_completion_percentage), 1)             AS expected_cmp_pct,
            ROUND(AVG(passer_rating), 1)                              AS ngs_passer_rating
        FROM ngs_passing
        WHERE player_gsis_id = ? AND season_type = 'REG'
        GROUP BY season
    """, [player_id]):
        s = row.pop("season")
        result.setdefault(s, {}).update({k: v for k, v in row.items() if v is not None})

    for row in safe_query("""
        SELECT season,
            ROUND(SUM(rush_yards_over_expected), 1)                   AS rush_yoe,
            ROUND(AVG(rush_yards_over_expected_per_att), 2)           AS rush_yoe_per_att,
            ROUND(AVG(efficiency), 1)                                 AS rush_efficiency,
            ROUND(AVG(avg_time_to_los), 2)                            AS avg_time_to_los,
            ROUND(AVG(percent_attempts_gte_eight_defenders), 1)       AS pct_vs_8_defenders
        FROM ngs_rushing
        WHERE player_gsis_id = ? AND season_type = 'REG'
        GROUP BY season
    """, [player_id]):
        s = row.pop("season")
        result.setdefault(s, {}).update({k: v for k, v in row.items() if v is not None})

    for row in safe_query("""
        SELECT season,
            ROUND(AVG(avg_separation), 2)                             AS avg_separation,
            ROUND(AVG(avg_cushion), 2)                                AS avg_cushion,
            ROUND(AVG(avg_intended_air_yards), 1)                     AS avg_target_depth,
            ROUND(AVG(avg_yac), 2)                                    AS avg_yac,
            ROUND(AVG(avg_yac_above_expectation), 2)                  AS avg_yac_above_exp,
            ROUND(AVG(catch_percentage), 1)                           AS catch_pct,
            ROUND(AVG(percent_share_of_intended_air_yards), 1)        AS air_yards_share
        FROM ngs_receiving
        WHERE player_gsis_id = ? AND season_type = 'REG'
        GROUP BY season
    """, [player_id]):
        s = row.pop("season")
        result.setdefault(s, {}).update({k: v for k, v in row.items() if v is not None})

    for s, cpoe in (cpoe_fallback or {}).items():
        d = result.setdefault(s, {})
        if d.get("cpoe") is None:
            d["cpoe"] = cpoe

    return result


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


def _get_pbp_stats(player_id: str) -> dict:
    """Every play-by-play-derived per-season stat family in TWO scans of plays.

    plays is the biggest table (1.3M rows) and has no per-player index, so each
    query against it is a full scan whose cost is dominated by the id columns
    compared in the WHERE plus the columns fetched for matching rows. The
    profile endpoint used to make nine of them (situational, WPA, kicking,
    punting, CPOE fallback, fumbles, penalties, defensive TDs, stuff rate).

    Two scans, split by match profile — measured faster than either nine
    narrow scans or one wide OR (a single OR forces fetching every family's
    columns for all matched rows, and a skill player matches thousands):
    - trio scan: passer/rusher/receiver families (many matched rows,
      touchdown/first-down/WPA/CPOE columns)
    - special scan: kicker/punter/penalty/defensive-TD families (few matched
      rows for most players, kicking/penalty columns)

    Each family keeps a presence guard (its old query's WHERE as a COUNT) so a
    season only receives that family's keys when the family actually had
    activity — exact parity with the separate queries this replaces.

    Notes carried over from the originals:
    - pass_touchdown / rush_touchdown, NOT touchdown: `touchdown` is true for
      ANY score on the play, so a red-zone pick-six would count as offensive.
    - WPA uses the split component matching the role (air_wpa passing,
      yac_wpa receiving, wpa rushing).
    - def_tds restricts to interception/fumble plays (not just
      return_touchdown = 1) to exclude punt/kick return TDs.
    - CPOE fallback needs >= 100 qualifying attempts in a season (nflfastR's
      model covers 2006+; NGS takes precedence — see _get_ngs).

    Returns {"situational": ..., "wpa": ..., "kicking": ..., "adv": ...,
    "cpoe": {season: cpoe}} — all keyed by season.
    """
    situational: dict[int, dict] = {}
    wpa:         dict[int, dict] = {}
    kicking:     dict[int, dict] = {}
    adv:         dict[int, dict] = {}
    cpoe:        dict[int, float] = {}

    trio_rows = safe_query("""
        WITH pp AS (
            SELECT season, passer_player_id, rusher_player_id, receiver_player_id,
                   pass_attempt, complete_pass, rush_attempt, sack, down, yardline_100,
                   passing_yards, rushing_yards, receiving_yards,
                   pass_touchdown, rush_touchdown, first_down_pass, first_down_rush,
                   air_wpa, yac_wpa, wpa, cpoe, fumble_lost
            FROM plays
            WHERE season_type = 'REG'
              AND (passer_player_id = ? OR rusher_player_id = ? OR receiver_player_id = ?)
        )
        SELECT season,
            COUNT(*) FILTER (WHERE rusher_player_id = q.pid) AS rusher_n,
            -- situational: longest / red zone / 3rd down / first downs
            MAX(CASE WHEN passer_player_id  = q.pid AND pass_attempt = 1 AND complete_pass = 1 THEN passing_yards   END) AS lng_pass,
            MAX(CASE WHEN rusher_player_id   = q.pid AND rush_attempt = 1                       THEN rushing_yards   END) AS lng_rush,
            MAX(CASE WHEN receiver_player_id = q.pid AND complete_pass = 1                      THEN receiving_yards END) AS lng_rec,
            COUNT(*) FILTER (WHERE passer_player_id = q.pid AND pass_attempt = 1 AND yardline_100 <= 20)                          AS rz_pass_att,
            SUM(CASE WHEN passer_player_id  = q.pid AND pass_attempt = 1 AND complete_pass = 1  AND yardline_100 <= 20 THEN 1 ELSE 0 END) AS rz_cmp,
            SUM(CASE WHEN passer_player_id  = q.pid AND pass_attempt = 1 AND pass_touchdown = 1 AND yardline_100 <= 20 THEN 1 ELSE 0 END) AS rz_pass_tds,
            COUNT(*) FILTER (WHERE receiver_player_id = q.pid AND pass_attempt = 1 AND yardline_100 <= 20)                        AS rz_targets,
            SUM(CASE WHEN receiver_player_id = q.pid AND pass_attempt = 1 AND pass_touchdown = 1 AND yardline_100 <= 20 THEN 1 ELSE 0 END) AS rz_rec_tds,
            COUNT(*) FILTER (WHERE rusher_player_id = q.pid AND rush_attempt = 1 AND yardline_100 <= 20)                          AS rz_carries,
            SUM(CASE WHEN rusher_player_id   = q.pid AND rush_attempt = 1 AND rush_touchdown = 1 AND yardline_100 <= 20 THEN 1 ELSE 0 END) AS rz_rush_tds,
            COUNT(*) FILTER (WHERE passer_player_id = q.pid AND pass_attempt = 1 AND down = 3)                                    AS third_pass_att,
            SUM(COALESCE(CASE WHEN passer_player_id  = q.pid AND pass_attempt = 1  AND down = 3 THEN first_down_pass END, 0))     AS third_pass_fd,
            COUNT(*) FILTER (WHERE receiver_player_id = q.pid AND pass_attempt = 1 AND down = 3)                                  AS third_targets,
            SUM(COALESCE(CASE WHEN receiver_player_id = q.pid AND complete_pass = 1 AND down = 3 THEN first_down_pass END, 0))    AS third_rec_fd,
            COUNT(*) FILTER (WHERE rusher_player_id = q.pid AND rush_attempt = 1 AND down = 3)                                    AS third_carries,
            SUM(COALESCE(CASE WHEN rusher_player_id   = q.pid AND rush_attempt = 1  AND down = 3 THEN first_down_rush END, 0))    AS third_rush_fd,
            SUM(COALESCE(CASE WHEN passer_player_id  = q.pid AND pass_attempt = 1  THEN first_down_pass END, 0)) AS fd_pass,
            SUM(COALESCE(CASE WHEN receiver_player_id = q.pid AND complete_pass = 1 THEN first_down_pass END, 0)) AS fd_rec,
            SUM(COALESCE(CASE WHEN rusher_player_id   = q.pid AND rush_attempt = 1  THEN first_down_rush END, 0)) AS fd_rush,
            -- WPA (split credit by role)
            ROUND(SUM(CASE WHEN passer_player_id   = q.pid AND pass_attempt  = 1 THEN COALESCE(air_wpa, 0) ELSE 0 END), 3) AS pass_wpa,
            ROUND(SUM(CASE WHEN receiver_player_id = q.pid AND complete_pass = 1 THEN COALESCE(yac_wpa, 0) ELSE 0 END), 3) AS rec_wpa,
            ROUND(SUM(CASE WHEN rusher_player_id   = q.pid AND rush_attempt  = 1 THEN COALESCE(wpa, 0)     ELSE 0 END), 3) AS rush_wpa,
            -- CPOE fallback for pre-NGS seasons
            ROUND(AVG(cpoe) FILTER (WHERE passer_player_id = q.pid AND pass_attempt = 1), 1) AS cpoe_fb,
            COUNT(cpoe)     FILTER (WHERE passer_player_id = q.pid AND pass_attempt = 1)     AS cpoe_n,
            -- fumbles lost / stuff rate
            SUM(CASE
                WHEN rusher_player_id   = q.pid AND rush_attempt  = 1 AND fumble_lost = 1 THEN 1
                WHEN receiver_player_id = q.pid AND complete_pass = 1 AND fumble_lost = 1 THEN 1
                WHEN passer_player_id   = q.pid AND sack          = 1 AND fumble_lost = 1 THEN 1
                ELSE 0 END) AS fumbles_lost,
            COUNT(*) FILTER (WHERE rusher_player_id = q.pid AND rush_attempt = 1 AND rushing_yards <= 0)                      AS stuffed,
            COUNT(*) FILTER (WHERE rusher_player_id = q.pid AND rush_attempt = 1)                                             AS carries_total,
            ROUND(100.0 * COUNT(*) FILTER (WHERE rusher_player_id = q.pid AND rush_attempt = 1 AND rushing_yards <= 0)
                        / NULLIF(COUNT(*) FILTER (WHERE rusher_player_id = q.pid AND rush_attempt = 1), 0), 1)                AS stuff_rate
        FROM pp CROSS JOIN (SELECT ? AS pid) q
        GROUP BY season
    """, [player_id] * 4)

    special_rows = safe_query("""
        WITH pp AS (
            SELECT season, kicker_player_id, punter_player_id, penalty_player_id, td_player_id,
                   penalty, penalty_type, penalty_yards,
                   return_touchdown, interception, fumble,
                   field_goal_attempt, field_goal_result, kick_distance,
                   punt_attempt, touchback, punt_inside_twenty, punt_blocked, return_yards
            FROM plays
            WHERE season_type = 'REG'
              AND (kicker_player_id = ? OR punter_player_id = ?
                   OR penalty_player_id = ? OR td_player_id = ?)
        )
        SELECT season,
            COUNT(*) FILTER (WHERE penalty = 1 AND penalty_player_id = q.pid)             AS penalties,
            COUNT(*) FILTER (WHERE kicker_player_id = q.pid AND field_goal_attempt = 1)   AS fg_n,
            COUNT(*) FILTER (WHERE punter_player_id = q.pid AND punt_attempt = 1)         AS punts,
            -- penalties / defensive TDs
            SUM(COALESCE(penalty_yards, 0)) FILTER (WHERE penalty = 1 AND penalty_player_id = q.pid)                          AS penalty_yards,
            COUNT(*) FILTER (WHERE penalty = 1 AND penalty_player_id = q.pid AND penalty_type = 'False Start')                AS false_starts,
            COUNT(*) FILTER (WHERE penalty = 1 AND penalty_player_id = q.pid AND penalty_type = 'Offensive Holding')          AS holding,
            COUNT(*) FILTER (WHERE td_player_id = q.pid AND return_touchdown = 1 AND (interception = 1 OR fumble = 1))        AS def_tds,
            -- kicker: field goals by distance bucket
            MAX(kick_distance) FILTER (WHERE kicker_player_id = q.pid AND field_goal_attempt = 1 AND field_goal_result = 'made') AS fg_long,
            COUNT(*) FILTER (WHERE kicker_player_id = q.pid AND field_goal_attempt = 1 AND kick_distance < 40)                                             AS fg_0_39_att,
            COUNT(*) FILTER (WHERE kicker_player_id = q.pid AND field_goal_attempt = 1 AND kick_distance < 40 AND field_goal_result = 'made')              AS fg_0_39_made,
            COUNT(*) FILTER (WHERE kicker_player_id = q.pid AND field_goal_attempt = 1 AND kick_distance BETWEEN 40 AND 49)                                AS fg_40_49_att,
            COUNT(*) FILTER (WHERE kicker_player_id = q.pid AND field_goal_attempt = 1 AND kick_distance BETWEEN 40 AND 49 AND field_goal_result = 'made') AS fg_40_49_made,
            COUNT(*) FILTER (WHERE kicker_player_id = q.pid AND field_goal_attempt = 1 AND kick_distance >= 50)                                            AS fg_50_att,
            COUNT(*) FILTER (WHERE kicker_player_id = q.pid AND field_goal_attempt = 1 AND kick_distance >= 50 AND field_goal_result = 'made')             AS fg_50_made,
            COUNT(*) FILTER (WHERE kicker_player_id = q.pid AND field_goal_attempt = 1 AND field_goal_result = 'blocked')                                  AS fg_blocked,
            -- punter: net = gross - return - 20*touchbacks (computed below)
            SUM(kick_distance)              FILTER (WHERE punter_player_id = q.pid AND punt_attempt = 1)                      AS gross_yards,
            SUM(COALESCE(return_yards, 0))  FILTER (WHERE punter_player_id = q.pid AND punt_attempt = 1)                      AS return_yards,
            COUNT(*) FILTER (WHERE punter_player_id = q.pid AND punt_attempt = 1 AND touchback = 1)                           AS punt_touchbacks,
            COUNT(*) FILTER (WHERE punter_player_id = q.pid AND punt_attempt = 1 AND punt_inside_twenty = 1)                  AS punt_inside_20,
            MAX(kick_distance)              FILTER (WHERE punter_player_id = q.pid AND punt_attempt = 1)                      AS punt_long,
            COUNT(*) FILTER (WHERE punter_player_id = q.pid AND punt_attempt = 1 AND punt_blocked = 1)                        AS punt_blocked
        FROM pp CROSS JOIN (SELECT ? AS pid) q
        GROUP BY season
    """, [player_id] * 5)

    _SITUATIONAL = ("lng_pass", "lng_rush", "lng_rec",
                    "rz_pass_att", "rz_cmp", "rz_pass_tds", "rz_targets", "rz_rec_tds",
                    "rz_carries", "rz_rush_tds",
                    "third_pass_att", "third_pass_fd", "third_targets", "third_rec_fd",
                    "third_carries", "third_rush_fd", "fd_pass", "fd_rec", "fd_rush")
    _FG_KEYS = ("fg_long", "fg_0_39_att", "fg_0_39_made", "fg_40_49_att", "fg_40_49_made",
                "fg_50_att", "fg_50_made", "fg_blocked")

    for row in trio_rows:
        s = int(row["season"])

        d = {}
        for k in _SITUATIONAL:
            v = row[k]
            if v is None:
                continue
            d[k] = int(v) if isinstance(v, float) and v.is_integer() else v
        situational.setdefault(s, {}).update(d)

        wpa[s] = {"pass_wpa": row["pass_wpa"], "rec_wpa": row["rec_wpa"], "rush_wpa": row["rush_wpa"]}
        adv.setdefault(s, {})["fumbles_lost"] = int(row["fumbles_lost"] or 0)

        if row["cpoe_n"] >= 100 and row["cpoe_fb"] is not None:
            cpoe[s] = row["cpoe_fb"]

        if row["rusher_n"]:
            d = adv.setdefault(s, {})
            d["stuffed"]       = int(row["stuffed"] or 0)
            d["carries_total"] = int(row["carries_total"] or 0)
            if row["stuff_rate"] is not None:
                d["stuff_rate"] = float(row["stuff_rate"])

    for row in special_rows:
        s = int(row["season"])

        if row["penalties"]:
            d = adv.setdefault(s, {})
            d["penalties"]     = int(row["penalties"])
            d["penalty_yards"] = int(row["penalty_yards"] or 0)
            d["false_starts"]  = int(row["false_starts"] or 0)
            d["holding"]       = int(row["holding"] or 0)

        if row["def_tds"]:
            adv.setdefault(s, {})["def_tds"] = int(row["def_tds"])

        if row["fg_n"]:
            kicking.setdefault(s, {}).update(
                {k: int(row[k]) for k in _FG_KEYS if row[k] is not None}
            )

        if row["punts"]:
            gross = row["gross_yards"] or 0
            ret = row["return_yards"] or 0
            tb = row["punt_touchbacks"] or 0
            d = kicking.setdefault(s, {})
            d["punt_net_yards"]  = int(gross - ret - 20 * tb)
            d["punt_inside_20"]  = int(row["punt_inside_20"] or 0)
            d["punt_touchbacks"] = int(tb)
            if row["punt_long"] is not None:
                d["punt_long"] = int(row["punt_long"])
            d["punt_blocked"] = int(row["punt_blocked"] or 0)

    return {"situational": situational, "wpa": wpa, "kicking": kicking, "adv": adv, "cpoe": cpoe}


def _get_target_shares(player_id: str) -> dict:
    """Target share & air yards share — the player's share of team targets/air
    yards in games they actually appeared in (handles mid-season trades
    correctly). pgs-based, so it stays separate from the plays scan above."""
    result: dict[int, dict] = {}
    for row in safe_query("""
        WITH player_games AS (
            SELECT pgs.game_id, pgs.season, pgs.team,
                   pgs.targets AS p_tgt, pgs.air_yards AS p_ay
            FROM player_game_stats pgs
            JOIN schedules s ON pgs.game_id = s.game_id AND s.game_type = 'REG'
            WHERE pgs.player_id = ?
        ),
        team_totals AS (
            SELECT pgs2.season, pg.team,
                   SUM(pgs2.targets)   AS team_tgt,
                   SUM(pgs2.air_yards) AS team_ay
            FROM player_game_stats pgs2
            JOIN player_games pg ON pgs2.game_id = pg.game_id AND pgs2.team = pg.team
            GROUP BY pgs2.season, pg.team
        ),
        player_season AS (
            SELECT season, SUM(p_tgt) AS player_tgt, SUM(p_ay) AS player_ay
            FROM player_games
            GROUP BY season
        )
        SELECT ps.season,
               ROUND(100.0 * ps.player_tgt / NULLIF(SUM(tt.team_tgt), 0), 1) AS target_share,
               ROUND(100.0 * ps.player_ay  / NULLIF(SUM(tt.team_ay),  0), 1) AS air_yards_share
        FROM player_season ps
        JOIN team_totals tt ON ps.season = tt.season
        -- SUM across stints: a traded player has one team_totals row per team,
        -- and joining on season alone fanned that out to multiple result rows —
        -- whichever arrived last won, nondeterministically (a share could even
        -- exceed 100%). The share is his totals over the combined team totals
        -- from games he appeared in.
        GROUP BY ps.season, ps.player_tgt, ps.player_ay
    """, [player_id]):
        s = int(row["season"])
        d = result.setdefault(s, {})
        if row["target_share"]    is not None: d["target_share"]    = float(row["target_share"])
        if row["air_yards_share"] is not None: d["air_yards_share"] = float(row["air_yards_share"])
    return result


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


@router.get("/players/{player_id}", response_model=PlayerProfile)
def get_player(player_id: str):
    profile_rows = query_to_dict(
        """
        SELECT
            player_id, player_name, position, team, jersey_number,
            headshot_url, height, weight, age, college,
            years_exp, entry_year, rookie_year, draft_club, draft_number
        FROM rosters
        WHERE player_id = ?
        ORDER BY season DESC
        LIMIT 1
        """,
        [player_id],
    )
    if not profile_rows:
        raise HTTPException(status_code=404, detail=f"Player {player_id} not found")

    profile = profile_rows[0]
    position = (profile.get("position") or "").upper()

    if position in _OL_POSITIONS:
        games = _get_snap_first_games(player_id, with_stats=False)
    elif position in {"K", "P"}:
        games = _get_snap_first_games(player_id, with_stats=True)
    else:
        # When roster data is absent for early seasons (r.team IS NULL), pgs.team is unreliable
        # (it reflects the away-team slot, not the player's actual team for home games).
        # Use the player's most-recent known team as a fallback before trusting pgs.team.
        profile_team = profile.get("team") or ""
        team_sel = f"""\
CASE
                    WHEN r.team IN (s.away_team, s.home_team)               THEN r.team
                    WHEN r.team IS NULL AND ? IN (s.away_team, s.home_team) THEN ?
                    WHEN pgs.team IN (s.away_team, s.home_team)             THEN pgs.team
                    ELSE COALESCE(r.team, pgs.team)
                END"""
        team_rank = f"""\
CASE
                        WHEN r.team = pgs.team AND pgs.team IN (s.away_team, s.home_team) THEN 0
                        WHEN r.team IN (s.away_team, s.home_team)                         THEN 1
                        WHEN r.team IS NULL AND ? IN (s.away_team, s.home_team)           THEN 2
                        WHEN pgs.team IN (s.away_team, s.home_team)                       THEN 3
                        ELSE 4
                    END"""
        stat_cols_csv = ", ".join(STAT_COLS)

        games = query_to_dict(
            f"""
            WITH {ROSTER_CTE},
            ranked AS (
                SELECT
                    pgs.game_id, pgs.season, pgs.week, pgs.player_id,
                    {team_sel} AS team,
                    s.away_team, s.home_team, s.gameday, s.away_score, s.home_score, s.game_type,
                    r.position, r.jersey_number, r.headshot_url,
                    {PGS_STAT_SEL},
                    ROW_NUMBER() OVER (
                        PARTITION BY pgs.game_id, pgs.player_id
                        ORDER BY {team_rank}
                    ) AS rn
                FROM player_game_stats pgs
                LEFT JOIN schedules s ON pgs.game_id = s.game_id
                LEFT JOIN roster r    ON pgs.player_id = r.player_id AND r.season = pgs.season
                WHERE pgs.player_id = ?
            )
            SELECT
                game_id, season, week, team,
                CASE WHEN team = home_team THEN away_team ELSE home_team END AS opponent,
                CASE WHEN team = home_team THEN 'home' ELSE 'away' END       AS location,
                gameday, away_score, home_score,
                CASE
                    WHEN away_score IS NULL                               THEN NULL
                    WHEN team = home_team AND home_score > away_score     THEN 'W'
                    WHEN team = away_team AND away_score > home_score     THEN 'W'
                    WHEN home_score = away_score                          THEN 'T'
                    ELSE 'L'
                END AS result,
                game_type,
                {stat_cols_csv},
                position, jersey_number, headshot_url
            FROM ranked
            WHERE rn = 1
            ORDER BY season, week
            """,
            [profile_team, profile_team, profile_team, player_id],
        )

    # Regular-season only, to reconcile with the situational/kicking/etc. stats
    # below (all REG-filtered) and with the ask-agent's get_player_overview.
    # Playoff games stay in `games` for the log — the frontend badges them by
    # game_type and shows a separate postseason section.
    reg_games = [g for g in games if g.get("game_type") == "REG"]
    season_totals = {col: sum(g[col] or 0 for g in reg_games) for col in STAT_COLS}

    # One scan of plays covers situational / WPA / kicking / most adv stats /
    # the CPOE fallback; target share is pgs-based and merges into adv.
    pbp = _get_pbp_stats(player_id)
    adv_stats = pbp["adv"]
    for s, d in _get_target_shares(player_id).items():
        adv_stats.setdefault(s, {}).update(d)

    return {
        **profile,
        "games_played": len(reg_games),
        "season_totals": season_totals,
        "games": games,
        "ngs": _get_ngs(player_id, pbp["cpoe"]),
        "snap_totals": _get_snap_totals(player_id),
        "situational": pbp["situational"],
        "kicking": pbp["kicking"],
        "wpa": pbp["wpa"],
        "adv_stats": adv_stats,
        "draft":          _get_draft_info(player_id),
        "combine":        _get_combine_data(player_id),
        "current_injury": _get_current_injury(player_id),
        "depth":          _get_current_depth(player_id),
        "awards":         _get_player_awards(player_id),
    }


# ── Supplemental vendor lookups ──────────────────────────────────────────────
# Each returns the dict (or None) for a single player. safe_query returns []
# on missing tables, so cold DBs that haven't ingested supplemental data
# yet just see null fields rather than errors.

def _get_draft_info(player_id: str) -> dict | None:
    # Vendor leaves car_av as NULL everywhere; w_av (Weighted Career AV) is
    # the populated PFR metric. Surface w_av under the same response key
    # so the frontend doesn't need to know about the rename.
    rows = safe_query("""
        SELECT season, round, pick, team, college, age,
               probowls, allpro,
               COALESCE(car_av, w_av) AS car_av,
               games
        FROM draft_picks
        WHERE gsis_id = ?
        LIMIT 1
    """, [player_id])
    return rows[0] if rows else None


def _get_combine_data(player_id: str) -> dict | None:
    """Combine joins on pfr_id, not gsis_id. id_map is the canonical bridge
    but its pfr_id coverage is spotty for pre-2010 players (only ~60%).
    draft_picks carries its own pfr_player_id at ~90% coverage, so fall
    back to it when id_map comes up empty."""
    rows = safe_query("""
        WITH p AS (
            SELECT COALESCE(
                (SELECT pfr_player_id FROM draft_picks
                  WHERE gsis_id = ? AND pfr_player_id IS NOT NULL LIMIT 1),
                (SELECT pfr_id FROM id_map
                  WHERE gsis_id = ? AND pfr_id IS NOT NULL LIMIT 1)
            ) AS pfr_id
        )
        SELECT c.draft_year, c.draft_round, c.draft_ovr, c.school, c.pos,
               c.ht, c.wt, c.forty, c.bench, c.vertical,
               c.broad_jump, c.cone, c.shuttle
        FROM combine_data c, p
        WHERE c.pfr_id = p.pfr_id
        LIMIT 1
    """, [player_id, player_id])
    return rows[0] if rows else None


def _get_current_injury(player_id: str) -> dict | None:
    """Most recent injury entry, regardless of how old. The UI annotates
    with the season+week so users see whether it's current or historical."""
    rows = safe_query("""
        SELECT season, week, team,
               report_primary_injury, report_secondary_injury, report_status,
               practice_primary_injury, practice_status,
               full_name, position, gsis_id
        FROM injuries
        WHERE gsis_id = ?
        ORDER BY season DESC, week DESC
        LIMIT 1
    """, [player_id])
    return rows[0] if rows else None


def _get_player_awards(player_id: str) -> list[dict]:
    """All major postseason voting awards for a player, ordered season DESC.
    Joins on gsis_id which is populated by the ingest-time name-to-roster
    join in `_load_player_awards`."""
    return safe_query("""
        SELECT season, award, team, position
        FROM player_awards
        WHERE gsis_id = ?
        ORDER BY season DESC, award
    """, [player_id])


def _get_current_depth(player_id: str) -> dict | None:
    """Most recent depth-chart slot, formation-agnostic. UI surfaces it as
    a badge (e.g. 'WR1' or 'LT')."""
    rows = safe_query("""
        SELECT season, week, club_code AS team, formation,
               depth_position, depth_team,
               gsis_id, full_name, position, jersey_number
        FROM depth_charts
        WHERE gsis_id = ?
        ORDER BY season DESC, week DESC
        LIMIT 1
    """, [player_id])
    return rows[0] if rows else None



# ── Comparable players ───────────────────────────────────────────────────────
# Reads from materialized tables maintained by comparables_builder (run during
# ingest). On a cold table the builder lazily rebuilds; thereafter the
# endpoint is a single keyed JOIN.

import comparables_builder


@router.get("/players/{player_id}/comparables", response_model=list[PlayerComparable])
def get_player_comparables(player_id: str, n: int = Query(default=8, ge=1, le=20)):
    return comparables_builder.read_or_materialize(player_id, n)


# ── Situational splits ───────────────────────────────────────────────────────
# The player's stat line conditioned on one dimension at a time (down, pass
# depth, location, game script, quarter, formation). Reads from the
# materialized player_splits table; self-heals on a cold table.

import splits_builder
import def_splits_builder


@router.get("/players/{player_id}/splits", response_model=list[PlayerSplit])
def get_player_splits(player_id: str):
    return splits_builder.read_or_materialize(player_id)


@router.get("/players/{player_id}/def-splits", response_model=list[DefensiveSplit])
def get_player_def_splits(player_id: str):
    """A defender's event line conditioned on one situational dimension."""
    return def_splits_builder.read_or_materialize(player_id)
