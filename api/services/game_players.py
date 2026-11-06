"""Game player selection, position groups and personnel labels; no HTTP or I/O."""

DEFENSE_POS = {"DE", "DT", "NT", "DL", "EDGE", "OLB", "ILB", "MLB", "LB", "CB", "DB", "FS", "SS", "S"}


def position_group(position: str | None) -> str | None:
    if not position:
        return None
    p = position.upper()
    if p == "QB":
        return "QB"
    if p in {"RB", "FB", "HB"}:
        return "RB"
    if p == "WR":
        return "WR"
    if p == "TE":
        return "TE"
    if p in DEFENSE_POS:
        return "DEF"
    if p == "K":
        return "K"
    return None


def offense_personnel(players: list[dict]) -> str | None:
    if not players:
        return None
    wr = sum(1 for p in players if (p.get("position") or "").upper() == "WR")
    te = sum(1 for p in players if (p.get("position") or "").upper() == "TE")
    rb = sum(1 for p in players if (p.get("position") or "").upper() in {"RB", "FB", "HB"})
    return f"{rb}{te} personnel" if rb or te or wr else "Offense"


def defense_personnel(players: list[dict]) -> str | None:
    if not players:
        return None
    dl = sum(1 for p in players if (p.get("position") or "").upper() in {"DE", "DT", "NT", "DL", "EDGE"})
    lb = sum(1 for p in players if (p.get("position") or "").upper() in {"OLB", "ILB", "MLB", "LB"})
    db = sum(1 for p in players if (p.get("position") or "").upper() in {"CB", "DB", "FS", "SS", "S", "NB"})
    if db >= 6:
        return "Dime"
    if db == 5:
        return "Nickel"
    if dl and lb:
        return f"{dl}-{lb}"
    return "Defense"


def lineup_players(rows: list[dict], team: str, unit: str) -> list[dict]:
    snap_col = "offense_snaps" if unit == "offense" else "defense_snaps"
    pct_col = "offense_pct" if unit == "offense" else "defense_pct"
    unit_rows = [r for r in rows if r["team"] == team and (r.get(snap_col) or 0) > 0]
    unit_rows.sort(key=lambda r: (r.get(snap_col) or 0, r.get("rating") or -1, r.get("player_name") or ""), reverse=True)
    players = []
    for r in unit_rows[:11]:
        players.append({
            "player_id": r.get("player_id"),
            "pfr_player_id": r.get("pfr_player_id"),
            "player_name": r.get("player_name") or "Unknown",
            "team": team,
            "position": r.get("position"),
            "position_group": r.get("position_group") or position_group(r.get("position")),
            "jersey_number": int(r["jersey_number"]) if r.get("jersey_number") is not None else None,
            "headshot_url": r.get("headshot_url"),
            "rating": r.get("rating"),
            "raw_score": r.get("raw_score"),
            "plays_counted": r.get("plays_counted"),
            "snaps": int(r.get(snap_col) or 0),
            "snap_pct": r.get(pct_col),
            "scored_td": bool(r.get("scored_td")),
        })
    return players


def rotation_players(rows: list[dict], team: str, starters: set[str | None]) -> list[dict]:
    rot = []
    for r in rows:
        if r["team"] != team or r.get("player_id") in starters:
            continue
        snaps = max(r.get("offense_snaps") or 0, r.get("defense_snaps") or 0, r.get("st_snaps") or 0)
        if snaps <= 0:
            continue
        pct = max(r.get("offense_pct") or 0, r.get("defense_pct") or 0, r.get("st_pct") or 0)
        rot.append({
            "player_id": r.get("player_id"),
            "pfr_player_id": r.get("pfr_player_id"),
            "player_name": r.get("player_name") or "Unknown",
            "team": team,
            "position": r.get("position"),
            "position_group": r.get("position_group") or position_group(r.get("position")),
            "jersey_number": int(r["jersey_number"]) if r.get("jersey_number") is not None else None,
            "headshot_url": r.get("headshot_url"),
            "rating": r.get("rating"),
            "raw_score": r.get("raw_score"),
            "plays_counted": r.get("plays_counted"),
            "snaps": int(snaps),
            "snap_pct": pct,
            "scored_td": bool(r.get("scored_td")),
        })
    rot.sort(key=lambda r: (r["rating"] is not None, r["rating"] or -1, r["snaps"]), reverse=True)
    return rot[:10]
