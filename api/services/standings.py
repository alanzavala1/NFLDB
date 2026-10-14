"""Regular-season division records from the published schedule."""
from collections import defaultdict

from config import CURRENT_SEASON, DIVISIONS
from database import query_to_dict


def get_standings(season: int | None = None) -> list[dict]:
    """Read regular-season standings for HTTP and assistant consumers."""
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
