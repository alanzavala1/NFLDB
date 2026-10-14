"""Pregame record annotations shared by schedule, game and team views."""


def attach_records(games: list[dict]) -> list[dict]:
    """Add away_record / home_record (entering each game) by walking weeks in order."""
    team_records: dict[str, tuple[int, int, int]] = {}  # team -> (W, L, T)

    def fmt(wlt: tuple[int, int, int]) -> str:
        w, l, t = wlt
        return f"{w}-{l}-{t}" if t else f"{w}-{l}"

    by_week: dict[int, list[dict]] = {}
    for g in games:
        by_week.setdefault(g["week"], []).append(g)

    for week in sorted(by_week):
        for g in by_week[week]:
            g["away_record"] = fmt(team_records.get(g["away_team"], (0, 0, 0)))
            g["home_record"] = fmt(team_records.get(g["home_team"], (0, 0, 0)))

        for g in by_week[week]:
            a, h = g["away_team"], g["home_team"]
            as_, hs = g["away_score"], g["home_score"]
            if as_ is None or hs is None:
                continue
            aw, al, at = team_records.get(a, (0, 0, 0))
            hw, hl, ht = team_records.get(h, (0, 0, 0))
            if as_ > hs:
                team_records[a] = (aw + 1, al, at)
                team_records[h] = (hw, hl + 1, ht)
            elif hs > as_:
                team_records[a] = (aw, al + 1, at)
                team_records[h] = (hw + 1, hl, ht)
            else:
                team_records[a] = (aw, al, at + 1)
                team_records[h] = (hw, hl, ht + 1)

    return games


def regular_record(games: list[dict], team: str) -> str:
    """Fallback record from the team service's completed regular-season games."""
    wins = losses = ties = 0
    for game in games:
        if game.get("game_type") != "REG":
            continue
        away_score, home_score = game.get("away_score"), game.get("home_score")
        if away_score is None or home_score is None:
            continue
        team_score = home_score if game.get("home_team") == team else away_score
        opp_score = away_score if game.get("home_team") == team else home_score
        if team_score > opp_score:
            wins += 1
        elif team_score < opp_score:
            losses += 1
        else:
            ties += 1
    return f"{wins}-{losses}-{ties}" if ties else f"{wins}-{losses}"
