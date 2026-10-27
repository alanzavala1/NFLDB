"""Player biography, game logs and season/stat-family composition."""
from database import query_to_dict
from sql_helpers import PGS_STAT_SEL, ROSTER_CTE, STAT_COLS
from services.receiving_coverage import mask_receiving_fields
from services.player_snaps import OL_POSITIONS as _OL_POSITIONS, _get_snap_first_games, _get_snap_totals
from services.player_tracking import _get_ngs
from services.player_advanced import _get_pbp_stats, _get_target_shares
from services.player_supplemental import _get_draft_info, _get_combine_data, _get_current_injury, _get_player_awards, _get_current_depth


def get_player_profile(player_id: str) -> dict | None:
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
        return None

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

    games = [mask_receiving_fields(g, g["season"]) for g in games]

    # Regular-season only, to reconcile with the situational/kicking/etc. stats
    # below (all REG-filtered) and with the ask-agent's get_player_overview.
    # Playoff games stay in `games` for the log — the frontend badges them by
    # game_type and shows a separate postseason section.
    reg_games = [g for g in games if g.get("game_type") == "REG"]
    season_totals = {col: sum(g[col] or 0 for g in reg_games) for col in STAT_COLS}
    for field in ("targets", "air_yards", "yac"):
        if any(g[field] is None for g in reg_games):
            season_totals[field] = None

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
        "situational": {s: mask_receiving_fields(d, s) for s, d in pbp["situational"].items()},
        "kicking": pbp["kicking"],
        "wpa": pbp["wpa"],
        "adv_stats": {s: mask_receiving_fields(d, s) for s, d in adv_stats.items()},
        "draft":          _get_draft_info(player_id),
        "combine":        _get_combine_data(player_id),
        "current_injury": _get_current_injury(player_id),
        "depth":          _get_current_depth(player_id),
        "awards":         _get_player_awards(player_id),
    }
