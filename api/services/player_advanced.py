"""Player data functions; HTTP-independent selection and assembly."""
from sql_helpers import safe_query


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
