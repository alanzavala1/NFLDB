"""Player profile, advanced stats, and comparable-player endpoints."""
import math

from fastapi import APIRouter, HTTPException, Query

from database import query_to_dict
from sql_helpers import PGS_STAT_SEL, ROSTER_CTE, STAT_COLS, safe_query

router = APIRouter()


# OL/K/P players: use snap_counts as the authoritative game-appearance source so the team per
# game is always correct (pgs.team is the away-team slot and is wrong for home players;
# ROSTER_CTE picks one team per player+season arbitrarily for multi-team players).
_OL_POSITIONS = {"C", "G", "T", "OT", "OG", "OL", "LS", "OC"}
_SNAP_FIRST_POSITIONS = _OL_POSITIONS | {"K", "P"}


def _get_ngs(player_id: str) -> dict:
    """Aggregate NGS weekly data by season for a player."""
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

    return result


def _get_snap_totals(player_id: str) -> dict:
    rows = safe_query("""
        WITH player_info AS (
            SELECT
                MAX(pfr_id)         AS pfr_id,
                MAX(player_name)    AS player_name
            FROM rosters
            WHERE player_id = ?
        ),
        player_seasons AS (
            SELECT season, team
            FROM rosters
            WHERE player_id = ?
            QUALIFY ROW_NUMBER() OVER (PARTITION BY player_id, season ORDER BY season DESC) = 1
        )
        SELECT sc.season,
            SUM(sc.offense_snaps)               AS offense_snaps,
            SUM(sc.defense_snaps)               AS defense_snaps,
            SUM(sc.st_snaps)                    AS st_snaps,
            ROUND(AVG(sc.offense_pct) * 100, 1) AS avg_offense_pct,
            ROUND(AVG(sc.defense_pct) * 100, 1) AS avg_defense_pct,
            ROUND(AVG(sc.st_pct) * 100, 1)      AS avg_st_pct
        FROM snap_counts sc, player_info pi
        WHERE (
            (pi.pfr_id IS NOT NULL AND sc.pfr_player_id = pi.pfr_id)
            OR
            (pi.pfr_id IS NULL
             AND LOWER(sc.player) = LOWER(pi.player_name)
             AND EXISTS (
                 SELECT 1 FROM player_seasons ps
                 WHERE ps.season = sc.season AND ps.team = sc.team
             ))
        )
        GROUP BY sc.season
    """, [player_id, player_id])
    return {r["season"]: r for r in rows}


def _get_situational_stats(player_id: str) -> dict:
    """Per-season situational stats from play-by-play: red zone, 3rd down, longest plays, first downs."""
    result: dict[int, dict] = {}
    pid = player_id

    def merge_rows(rows: list[dict]) -> None:
        for row in rows:
            s = row.pop("season", None)
            if s is None:
                continue
            cleaned = {}
            for k, v in row.items():
                if v is None:
                    continue
                cleaned[k] = int(v) if isinstance(v, float) and v.is_integer() else v
            result.setdefault(int(s), {}).update(cleaned)

    # Longest completions / rushes / receptions
    merge_rows(safe_query("""
        WITH pp AS (
            SELECT * FROM plays
            WHERE (passer_player_id = ? OR rusher_player_id = ? OR receiver_player_id = ?)
              AND season_type = 'REG'
        )
        SELECT season,
            MAX(CASE WHEN passer_player_id  = ? AND pass_attempt = 1 AND complete_pass = 1 THEN passing_yards   END) AS lng_pass,
            MAX(CASE WHEN rusher_player_id   = ? AND rush_attempt = 1                       THEN rushing_yards   END) AS lng_rush,
            MAX(CASE WHEN receiver_player_id = ? AND complete_pass = 1                      THEN receiving_yards END) AS lng_rec
        FROM pp GROUP BY season
    """, [pid, pid, pid, pid, pid, pid]))

    # Red zone (inside opponent 20 = yardline_100 <= 20)
    merge_rows(safe_query("""
        WITH pp AS (
            SELECT * FROM plays
            WHERE (passer_player_id = ? OR rusher_player_id = ? OR receiver_player_id = ?)
              AND yardline_100 <= 20
              AND season_type = 'REG'
        )
        SELECT season,
            COUNT(*)  FILTER (WHERE passer_player_id  = ? AND pass_attempt = 1)                        AS rz_pass_att,
            SUM(CASE WHEN passer_player_id  = ? AND pass_attempt = 1 AND complete_pass = 1 THEN 1 ELSE 0 END) AS rz_cmp,
            SUM(CASE WHEN passer_player_id  = ? AND pass_attempt = 1 AND touchdown = 1     THEN 1 ELSE 0 END) AS rz_pass_tds,
            COUNT(*)  FILTER (WHERE receiver_player_id = ? AND pass_attempt = 1)                       AS rz_targets,
            SUM(CASE WHEN receiver_player_id = ? AND pass_attempt = 1 AND touchdown = 1    THEN 1 ELSE 0 END) AS rz_rec_tds,
            COUNT(*)  FILTER (WHERE rusher_player_id   = ? AND rush_attempt = 1)                       AS rz_carries,
            SUM(CASE WHEN rusher_player_id   = ? AND rush_attempt = 1 AND touchdown = 1    THEN 1 ELSE 0 END) AS rz_rush_tds
        FROM pp GROUP BY season
    """, [pid, pid, pid, pid, pid, pid, pid, pid, pid, pid]))

    # 3rd down
    merge_rows(safe_query("""
        WITH pp AS (
            SELECT * FROM plays
            WHERE (passer_player_id = ? OR rusher_player_id = ? OR receiver_player_id = ?)
              AND down = 3
              AND season_type = 'REG'
        )
        SELECT season,
            COUNT(*)  FILTER (WHERE passer_player_id  = ? AND pass_attempt = 1)                                          AS third_pass_att,
            SUM(COALESCE(CASE WHEN passer_player_id  = ? AND pass_attempt = 1  THEN first_down_pass END, 0))              AS third_pass_fd,
            COUNT(*)  FILTER (WHERE receiver_player_id = ? AND pass_attempt = 1)                                          AS third_targets,
            SUM(COALESCE(CASE WHEN receiver_player_id = ? AND complete_pass = 1 THEN first_down_pass END, 0))             AS third_rec_fd,
            COUNT(*)  FILTER (WHERE rusher_player_id   = ? AND rush_attempt = 1)                                          AS third_carries,
            SUM(COALESCE(CASE WHEN rusher_player_id   = ? AND rush_attempt = 1  THEN first_down_rush END, 0))             AS third_rush_fd
        FROM pp GROUP BY season
    """, [pid, pid, pid, pid, pid, pid, pid, pid, pid]))

    # First downs generated
    merge_rows(safe_query("""
        WITH pp AS (
            SELECT * FROM plays
            WHERE (passer_player_id = ? OR rusher_player_id = ? OR receiver_player_id = ?)
              AND season_type = 'REG'
        )
        SELECT season,
            SUM(COALESCE(CASE WHEN passer_player_id  = ? AND pass_attempt = 1  THEN first_down_pass END, 0)) AS fd_pass,
            SUM(COALESCE(CASE WHEN receiver_player_id = ? AND complete_pass = 1 THEN first_down_pass END, 0)) AS fd_rec,
            SUM(COALESCE(CASE WHEN rusher_player_id   = ? AND rush_attempt = 1  THEN first_down_rush END, 0)) AS fd_rush
        FROM pp GROUP BY season
    """, [pid, pid, pid, pid, pid, pid]))

    return result


def _get_player_advanced_stats(player_id: str) -> dict:
    """Per-season: fumbles lost, target share, air yards share, stuff rate."""
    result: dict[int, dict] = {}
    pid = player_id

    # Fumbles lost — rusher fumbles on runs, receiver fumbles on catches, QB fumbles on sacks
    for row in safe_query("""
        SELECT season,
            SUM(CASE
                WHEN rusher_player_id   = ? AND rush_attempt  = 1 AND fumble_lost = 1 THEN 1
                WHEN receiver_player_id = ? AND complete_pass = 1 AND fumble_lost = 1 THEN 1
                WHEN passer_player_id   = ? AND sack          = 1 AND fumble_lost = 1 THEN 1
                ELSE 0 END) AS fumbles_lost
        FROM plays
        WHERE (rusher_player_id = ? OR receiver_player_id = ? OR passer_player_id = ?)
          AND season_type = 'REG'
        GROUP BY season
    """, [pid, pid, pid, pid, pid, pid]):
        s = int(row["season"])
        result.setdefault(s, {})["fumbles_lost"] = int(row["fumbles_lost"] or 0)

    # Target share & air yards share — player's share of team targets/air yards
    # in games the player actually appeared in (handles mid-season trades correctly)
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
               ROUND(100.0 * ps.player_tgt / NULLIF(tt.team_tgt, 0), 1) AS target_share,
               ROUND(100.0 * ps.player_ay  / NULLIF(tt.team_ay,  0), 1) AS air_yards_share
        FROM player_season ps
        JOIN team_totals tt ON ps.season = tt.season
    """, [pid]):
        s = int(row["season"])
        d = result.setdefault(s, {})
        if row["target_share"]    is not None: d["target_share"]    = float(row["target_share"])
        if row["air_yards_share"] is not None: d["air_yards_share"] = float(row["air_yards_share"])

    # Stuff rate — % of rush carries stopped at or behind the line of scrimmage
    for row in safe_query("""
        SELECT season,
            COUNT(*) FILTER (WHERE rush_attempt = 1 AND rushing_yards <= 0) AS stuffed,
            COUNT(*) FILTER (WHERE rush_attempt = 1)                         AS carries_total,
            ROUND(100.0 * COUNT(*) FILTER (WHERE rush_attempt = 1 AND rushing_yards <= 0)
                        / NULLIF(COUNT(*) FILTER (WHERE rush_attempt = 1), 0), 1) AS stuff_rate
        FROM plays
        WHERE rusher_player_id = ? AND season_type = 'REG'
        GROUP BY season
    """, [pid]):
        s = int(row["season"])
        d = result.setdefault(s, {})
        d["stuffed"]        = int(row["stuffed"] or 0)
        d["carries_total"]  = int(row["carries_total"] or 0)
        if row["stuff_rate"] is not None: d["stuff_rate"] = float(row["stuff_rate"])

    return result


def _get_player_wpa(player_id: str) -> dict:
    """Per-season WPA attribution from play-by-play using proper split credit."""
    result: dict[int, dict] = {}
    pid = player_id

    for row in safe_query("""
        SELECT season, ROUND(SUM(COALESCE(air_wpa, 0)), 3) AS pass_wpa
        FROM plays
        WHERE passer_player_id = ? AND pass_attempt = 1 AND season_type = 'REG'
        GROUP BY season
    """, [pid]):
        s = int(row["season"])
        result.setdefault(s, {})["pass_wpa"] = row["pass_wpa"]

    for row in safe_query("""
        SELECT season, ROUND(SUM(COALESCE(yac_wpa, 0)), 3) AS rec_wpa
        FROM plays
        WHERE receiver_player_id = ? AND complete_pass = 1 AND season_type = 'REG'
        GROUP BY season
    """, [pid]):
        s = int(row["season"])
        result.setdefault(s, {})["rec_wpa"] = row["rec_wpa"]

    for row in safe_query("""
        SELECT season, ROUND(SUM(COALESCE(wpa, 0)), 3) AS rush_wpa
        FROM plays
        WHERE rusher_player_id = ? AND rush_attempt = 1 AND season_type = 'REG'
        GROUP BY season
    """, [pid]):
        s = int(row["season"])
        result.setdefault(s, {})["rush_wpa"] = row["rush_wpa"]

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

    return query_to_dict(f"""
        WITH player_info AS (
            SELECT MAX(pfr_id) AS pfr_id, MAX(player_name) AS player_name
            FROM rosters WHERE player_id = ?
        ),
        player_all_teams AS (
            SELECT DISTINCT season, team FROM rosters WHERE player_id = ?
        ),
        player_roster AS (
            SELECT season, team, position, jersey_number, headshot_url
            FROM rosters WHERE player_id = ?
            QUALIFY ROW_NUMBER() OVER (PARTITION BY player_id, season ORDER BY season DESC) = 1
        ),
        player_snaps AS (
            SELECT sc.game_id, sc.season, sc.team
            FROM snap_counts sc, player_info pi
            WHERE (
                (pi.pfr_id IS NOT NULL AND sc.pfr_player_id = pi.pfr_id)
                OR
                (pi.pfr_id IS NULL
                 AND LOWER(sc.player) = LOWER(pi.player_name)
                 AND EXISTS (
                     SELECT 1 FROM player_all_teams pat
                     WHERE pat.season = sc.season AND pat.team = sc.team
                 ))
            )
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
    """, [player_id, player_id, player_id] + pgs_param)


@router.get("/players/{player_id}")
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

    season_totals = {col: sum(g[col] or 0 for g in games) for col in STAT_COLS}

    return {
        **profile,
        "games_played": len(games),
        "season_totals": season_totals,
        "games": games,
        "ngs": _get_ngs(player_id),
        "snap_totals": _get_snap_totals(player_id),
        "situational": _get_situational_stats(player_id),
        "wpa": _get_player_wpa(player_id),
        "adv_stats": _get_player_advanced_stats(player_id),
    }


# ── Comparable players (cosine similarity over z-scored per-game rates) ──────

def _comp_pos_group(pos: str | None, att: int, carries: int, tgts: int) -> str:
    if pos == 'QB': return 'QB'
    if pos in ('RB', 'FB'): return 'RB'
    if pos in ('WR', 'TE'): return 'WRTE'
    if att > carries and att > tgts and att >= 50: return 'QB'
    if carries >= tgts and carries >= 50: return 'RB'
    if tgts >= 30: return 'WRTE'
    return 'OTHER'


def _comp_feature_vec(r: dict, pg: str) -> list[float]:
    g   = max(r['games'],   1)
    att = max(r['att'],     1)
    car = max(r['carries'], 1)
    tgt = max(r['tgts'],    1)
    rec = max(r['rec'],     1)
    if pg == 'QB':
        return [
            r['cmp']      / att,
            r['pass_yds'] / att,
            r['pass_tds'] / att,
            r['ints']     / att,
            r['pass_epa'] / att,
            r['rush_yds'] / g,
            r['rush_tds'] / g,
        ]
    elif pg == 'RB':
        return [
            r['rush_yds'] / car,
            r['rush_tds'] / car,
            r['rush_yds'] / g,
            r['rush_epa'] / car,
            r['rec_yds']  / g,
            r['rec']      / g,
            r['tgts']     / g,
        ]
    else:
        return [
            r['rec']     / tgt,
            r['rec_yds'] / rec,
            r['rec_tds'] / rec,
            r['rec_yds'] / g,
            r['rec_epa'] / tgt,
            r['air_yds'] / tgt,
            r['yac']     / rec,
        ]


def _zscore_normalize(vecs: list[list[float]]) -> list[list[float]]:
    if not vecs: return vecs
    n_feat = len(vecs[0])
    out = [list(v) for v in vecs]
    for j in range(n_feat):
        vals = [v[j] for v in vecs]
        mu  = sum(vals) / len(vals)
        std = math.sqrt(sum((x - mu) ** 2 for x in vals) / len(vals))
        for i in range(len(out)):
            out[i][j] = (out[i][j] - mu) / std if std > 0 else 0.0
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0: return 0.0
    return dot / (mag_a * mag_b)


def _get_player_comparables(player_id: str, n: int = 8) -> list[dict]:
    rows = safe_query("""
        WITH recent_roster AS (
            SELECT player_id, position, team, headshot_url
            FROM rosters
            QUALIFY ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY season DESC) = 1
        ),
        career AS (
            SELECT
                pgs.player_id,
                MAX(pgs.player_name)          AS player_name,
                COUNT(DISTINCT pgs.game_id)   AS games,
                MIN(pgs.season)               AS first_season,
                MAX(pgs.season)               AS last_season,
                SUM(pgs.attempts)             AS att,
                SUM(pgs.completions)          AS cmp,
                SUM(pgs.pass_yards)           AS pass_yds,
                SUM(pgs.pass_tds)             AS pass_tds,
                SUM(pgs.interceptions_thrown) AS ints,
                SUM(pgs.pass_epa)             AS pass_epa,
                SUM(pgs.carries)              AS carries,
                SUM(pgs.rush_yards)           AS rush_yds,
                SUM(pgs.rush_tds)             AS rush_tds,
                SUM(pgs.rush_epa)             AS rush_epa,
                SUM(pgs.targets)              AS tgts,
                SUM(pgs.receptions)           AS rec,
                SUM(pgs.rec_yards)            AS rec_yds,
                SUM(pgs.rec_tds)              AS rec_tds,
                SUM(pgs.rec_epa)              AS rec_epa,
                SUM(pgs.air_yards)            AS air_yds,
                SUM(pgs.yac)                  AS yac
            FROM player_game_stats pgs
            JOIN schedules s ON pgs.game_id = s.game_id AND s.game_type = 'REG'
            GROUP BY pgs.player_id
            HAVING COUNT(DISTINCT pgs.game_id) >= 16
        )
        SELECT c.*, r.position, r.team, r.headshot_url
        FROM career c
        LEFT JOIN recent_roster r ON r.player_id = c.player_id
    """)

    if not rows:
        return []

    target = next((r for r in rows if r['player_id'] == player_id), None)
    if target is None:
        return []

    tpg = _comp_pos_group(target.get('position'), target['att'], target['carries'], target['tgts'])
    if tpg == 'OTHER':
        return []

    pool = [r for r in rows if _comp_pos_group(r.get('position'), r['att'], r['carries'], r['tgts']) == tpg]

    # Minimum sample filters per position
    min_att = {'QB': 200, 'RB': 0, 'WRTE': 0}
    min_car = {'QB': 0, 'RB': 100, 'WRTE': 0}
    min_tgt = {'QB': 0, 'RB': 0, 'WRTE': 50}
    pool = [r for r in pool
            if r['att'] >= min_att[tpg]
            and r['carries'] >= min_car[tpg]
            and r['tgts'] >= min_tgt[tpg]]

    if len(pool) < 2:
        return []

    vecs = [_comp_feature_vec(r, tpg) for r in pool]
    normed = _zscore_normalize(vecs)

    target_idx = next((i for i, r in enumerate(pool) if r['player_id'] == player_id), None)
    if target_idx is None:
        return []

    target_vec = normed[target_idx]

    scored = []
    for i, (r, v) in enumerate(zip(pool, normed)):
        if r['player_id'] == player_id:
            continue
        sim = max(0.0, _cosine(target_vec, v))
        scored.append((sim, r))

    scored.sort(key=lambda x: x[0], reverse=True)

    result = []
    for sim, r in scored[:n]:
        result.append({
            'player_id':    r['player_id'],
            'player_name':  r['player_name'],
            'position':     r.get('position'),
            'team':         r.get('team'),
            'headshot_url': r.get('headshot_url'),
            'similarity':   round(sim * 100, 1),
            'games':        r['games'],
            'first_season': r['first_season'],
            'last_season':  r['last_season'],
            'pass_yards':   r['pass_yds'],
            'pass_tds':     r['pass_tds'],
            'rush_yards':   r['rush_yds'],
            'rush_tds':     r['rush_tds'],
            'carries':      r['carries'],
            'rec_yards':    r['rec_yds'],
            'rec_tds':      r['rec_tds'],
            'targets':      r['tgts'],
            'att':          r['att'],
            'cmp':          r['cmp'],
            'ints':         r['ints'],
        })
    return result


@router.get("/players/{player_id}/comparables")
def get_player_comparables(player_id: str, n: int = Query(default=8, ge=1, le=20)):
    return _get_player_comparables(player_id, n)
