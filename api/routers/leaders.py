"""Season-level league endpoints: leaders, WPA leaders, standings, search."""
from collections import defaultdict

from fastapi import APIRouter, Query

from config import CURRENT_SEASON, DIVISIONS, TEAM_NAMES
from database import query_to_dict
from sql_helpers import ROSTER_CTE, safe_query

router = APIRouter()


@router.get("/leaders")
def get_leaders(season: int = Query(default=None)):
    if season is None:
        season = CURRENT_SEASON
    rows = query_to_dict(
        f"""
        WITH {ROSTER_CTE},
        stats AS (
            SELECT
                pgs.player_id,
                MAX(pgs.player_name)              AS player_name,
                COUNT(DISTINCT pgs.game_id)       AS games_played,
                SUM(pgs.attempts)                 AS attempts,
                SUM(pgs.completions)              AS completions,
                SUM(pgs.pass_yards)               AS pass_yards,
                SUM(pgs.pass_tds)                 AS pass_tds,
                SUM(pgs.interceptions_thrown)     AS interceptions_thrown,
                SUM(pgs.sacks_taken)              AS sacks_taken,
                SUM(pgs.carries)                  AS carries,
                SUM(pgs.rush_yards)               AS rush_yards,
                SUM(pgs.rush_tds)                 AS rush_tds,
                SUM(pgs.targets)                  AS targets,
                SUM(pgs.receptions)               AS receptions,
                SUM(pgs.rec_yards)                AS rec_yards,
                SUM(pgs.rec_tds)                  AS rec_tds,
                SUM(pgs.yac)                      AS yac,
                SUM(pgs.pass_epa)                 AS pass_epa,
                SUM(pgs.rush_epa)                 AS rush_epa,
                SUM(pgs.rec_epa)                  AS rec_epa,
                SUM(pgs.air_yards)                AS air_yards,
                SUM(pgs.solo_tackles)             AS solo_tackles,
                SUM(pgs.assist_tackles)           AS assist_tackles,
                SUM(pgs.tackles_for_loss)         AS tackles_for_loss,
                SUM(pgs.sacks)                    AS sacks,
                SUM(pgs.qb_hits)                  AS qb_hits,
                SUM(pgs.def_interceptions)        AS def_interceptions,
                SUM(pgs.pass_breakups)            AS pass_breakups,
                SUM(pgs.forced_fumbles)           AS forced_fumbles,
                SUM(pgs.fumble_recoveries)        AS fumble_recoveries,
                SUM(pgs.fg_att)                   AS fg_att,
                SUM(pgs.fg_made)                  AS fg_made,
                SUM(pgs.xp_att)                   AS xp_att,
                SUM(pgs.xp_made)                  AS xp_made,
                SUM(pgs.punts)                    AS punts,
                SUM(pgs.punt_yards)               AS punt_yards
            FROM player_game_stats pgs
            JOIN schedules sch ON pgs.game_id = sch.game_id AND sch.game_type = 'REG'
            WHERE pgs.season = ?
            GROUP BY pgs.player_id
        )
        SELECT s.*, r.position, r.team, r.headshot_url
        FROM stats s
        LEFT JOIN roster r ON r.player_id = s.player_id AND r.season = ?
        """,
        [season, season],
    )
    return rows


@router.get("/wpa-leaders")
def get_wpa_leaders(season: int = Query(default=None)):
    if season is None:
        season = CURRENT_SEASON

    passing = safe_query(f"""
        WITH {ROSTER_CTE},
        stats AS (
            SELECT passer_player_id AS player_id,
                   MAX(passer_player_name) AS player_name,
                   ROUND(SUM(COALESCE(air_wpa, 0)), 3) AS wpa,
                   COUNT(DISTINCT game_id) AS games_played,
                   COUNT(*) FILTER (WHERE pass_attempt = 1) AS attempts
            FROM plays
            WHERE season = ? AND season_type = 'REG'
              AND pass_attempt = 1 AND passer_player_id IS NOT NULL
            GROUP BY passer_player_id
            HAVING COUNT(*) FILTER (WHERE pass_attempt = 1) >= 50
        )
        SELECT stats.player_id, stats.player_name, r.position, r.team, r.headshot_url,
               stats.wpa, stats.games_played, stats.attempts
        FROM stats
        LEFT JOIN roster r ON r.player_id = stats.player_id AND r.season = ?
        ORDER BY wpa DESC
        LIMIT 30
    """, [season, season])

    rushing = safe_query(f"""
        WITH {ROSTER_CTE},
        stats AS (
            SELECT rusher_player_id AS player_id,
                   MAX(rusher_player_name) AS player_name,
                   ROUND(SUM(COALESCE(wpa, 0)), 3) AS wpa,
                   COUNT(DISTINCT game_id) AS games_played,
                   COUNT(*) AS carries
            FROM plays
            WHERE season = ? AND season_type = 'REG'
              AND rush_attempt = 1 AND rusher_player_id IS NOT NULL
            GROUP BY rusher_player_id
            HAVING COUNT(*) >= 50
        )
        SELECT stats.player_id, stats.player_name, r.position, r.team, r.headshot_url,
               stats.wpa, stats.games_played, stats.carries
        FROM stats
        LEFT JOIN roster r ON r.player_id = stats.player_id AND r.season = ?
        ORDER BY wpa DESC
        LIMIT 30
    """, [season, season])

    receiving = safe_query(f"""
        WITH {ROSTER_CTE},
        stats AS (
            SELECT receiver_player_id AS player_id,
                   MAX(receiver_player_name) AS player_name,
                   ROUND(SUM(COALESCE(yac_wpa, 0)), 3) AS wpa,
                   COUNT(DISTINCT game_id) AS games_played,
                   COUNT(*) FILTER (WHERE complete_pass = 1) AS receptions
            FROM plays
            WHERE season = ? AND season_type = 'REG'
              AND complete_pass = 1 AND receiver_player_id IS NOT NULL
            GROUP BY receiver_player_id
            HAVING COUNT(*) FILTER (WHERE complete_pass = 1) >= 20
        )
        SELECT stats.player_id, stats.player_name, r.position, r.team, r.headshot_url,
               stats.wpa, stats.games_played, stats.receptions
        FROM stats
        LEFT JOIN roster r ON r.player_id = stats.player_id AND r.season = ?
        ORDER BY wpa DESC
        LIMIT 30
    """, [season, season])

    return {"passing": passing, "rushing": rushing, "receiving": receiving}


@router.get("/standings")
def get_standings(season: int = Query(default=None)):
    if season is None:
        season = CURRENT_SEASON

    games = query_to_dict(
        "SELECT away_team, home_team, away_score, home_score, week FROM schedules WHERE season = ? AND game_type = 'REG' ORDER BY week",
        [season],
    )

    records: dict = defaultdict(lambda: {
        'w': 0, 'l': 0, 't': 0, 'pf': 0, 'pa': 0,
        'home_w': 0, 'home_l': 0, 'home_t': 0,
        'away_w': 0, 'away_l': 0, 'away_t': 0,
        'div_w':  0, 'div_l':  0, 'div_t':  0,
        'results': [],
    })

    all_teams: set[str] = set()
    for g in games:
        all_teams.add(g['away_team']); all_teams.add(g['home_team'])
        if g['away_score'] is None or g['home_score'] is None:
            continue
        a, h, as_, hs = g['away_team'], g['home_team'], g['away_score'], g['home_score']
        a_res = 'W' if as_ > hs else ('L' if hs > as_ else 'T')
        h_res = 'L' if as_ > hs else ('W' if hs > as_ else 'T')

        for team, res, home in [(a, a_res, False), (h, h_res, True)]:
            r = records[team]
            pfx = 'home_' if home else 'away_'
            own_score = hs if home else as_
            opp_score = as_ if home else hs
            r['pf'] += own_score; r['pa'] += opp_score
            r['results'].append(res)
            if res == 'W':   r['w'] += 1; r[pfx + 'w'] += 1
            elif res == 'L': r['l'] += 1; r[pfx + 'l'] += 1
            else:            r['t'] += 1; r[pfx + 't'] += 1

        a_div, h_div = DIVISIONS.get(a), DIVISIONS.get(h)
        if a_div and a_div == h_div:
            if a_res == 'W':   records[a]['div_w'] += 1; records[h]['div_l'] += 1
            elif a_res == 'L': records[a]['div_l'] += 1; records[h]['div_w'] += 1
            else:              records[a]['div_t'] += 1; records[h]['div_t'] += 1

    def fmt(w: int, l: int, t: int) -> str:
        return f"{w}-{l}-{t}" if t else f"{w}-{l}"

    def streak(results: list) -> str:
        if not results: return '—'
        cur = results[-1]; cnt = 0
        for r in reversed(results):
            if r == cur: cnt += 1
            else: break
        return f"{cur}{cnt}"

    division_order = [
        'AFC East', 'AFC North', 'AFC South', 'AFC West',
        'NFC East', 'NFC North', 'NFC South', 'NFC West',
    ]
    by_div: dict[str, list] = {d: [] for d in division_order}

    for team in all_teams:
        div = DIVISIONS.get(team)
        if not div or div not in by_div:
            continue
        r = records[team]
        gp = r['w'] + r['l'] + r['t']
        pct = (r['w'] + 0.5 * r['t']) / gp if gp else 0.0
        by_div[div].append({
            'team': team,
            'w': r['w'], 'l': r['l'], 't': r['t'],
            'pct': round(pct, 3),
            'pf': r['pf'], 'pa': r['pa'],
            'home': fmt(r['home_w'], r['home_l'], r['home_t']),
            'away': fmt(r['away_w'], r['away_l'], r['away_t']),
            'div':  fmt(r['div_w'],  r['div_l'],  r['div_t']),
            'strk': streak(r['results']),
        })

    result = []
    for div in division_order:
        teams = sorted(by_div[div], key=lambda t: (-t['pct'], -(t['pf'] - t['pa'])))
        if teams:
            lw, ll = teams[0]['w'], teams[0]['l']
            for t in teams:
                gb = ((lw - t['w']) + (t['l'] - ll)) / 2
                t['gb'] = '—' if gb == 0 else (f"{gb:.1f}".rstrip('0').rstrip('.') if gb % 1 else str(int(gb)))
        result.append({'division': div, 'teams': teams})

    return result


@router.get("/search")
def search(q: str = Query(..., min_length=1)):
    q = q.strip()
    if not q:
        return []

    ql = q.lower()

    # Team results — match abbreviation prefix or anywhere in full name
    teams = [
        {"type": "team", "id": abbrev, "name": name, "position": None, "team": abbrev, "headshot_url": None}
        for abbrev, name in TEAM_NAMES.items()
        if ql in abbrev.lower() or ql in name.lower()
    ][:3]

    # Player results — ILIKE match, deduplicated to most recent roster entry,
    # ranked: exact match → starts-with → contains
    players = safe_query(
        """
        SELECT
            player_id    AS id,
            player_name  AS name,
            position,
            team,
            headshot_url,
            CASE
                WHEN LOWER(player_name) = LOWER(?)            THEN 0
                WHEN LOWER(player_name) LIKE LOWER(?) || '%'  THEN 1
                ELSE 2
            END AS rank
        FROM rosters
        WHERE player_name ILIKE ?
        QUALIFY ROW_NUMBER() OVER (PARTITION BY player_id ORDER BY season DESC) = 1
        ORDER BY rank, player_name
        LIMIT 8
        """,
        [q, q, f"%{q}%"],
    )

    player_results = [
        {"type": "player", "id": p["id"], "name": p["name"],
         "position": p["position"], "team": p["team"], "headshot_url": p["headshot_url"]}
        for p in players
    ]

    return (teams + player_results)[:10]
