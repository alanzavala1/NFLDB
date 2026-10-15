"""Play-derived offensive fallback, defensive events and special-teams statistics."""
from collections import namedtuple

import pandas as pd

from pipeline.normalization import merge_all_stats


PlayerSlot = namedtuple("PlayerSlot", ["id_col", "name_col", "team_col", "stat", "weight"])


DEFENSIVE_SLOTS = [
    PlayerSlot("solo_tackle_1_player_id",          "solo_tackle_1_player_name",          "defteam",                "solo_tackles",      1.0),
    PlayerSlot("solo_tackle_2_player_id",          "solo_tackle_2_player_name",          "defteam",                "solo_tackles",      1.0),
    PlayerSlot("assist_tackle_1_player_id",        "assist_tackle_1_player_name",        "defteam",                "assist_tackles",    1.0),
    PlayerSlot("assist_tackle_2_player_id",        "assist_tackle_2_player_name",        "defteam",                "assist_tackles",    1.0),
    PlayerSlot("assist_tackle_3_player_id",        "assist_tackle_3_player_name",        "defteam",                "assist_tackles",    1.0),
    PlayerSlot("assist_tackle_4_player_id",        "assist_tackle_4_player_name",        "defteam",                "assist_tackles",    1.0),
    PlayerSlot("tackle_for_loss_1_player_id",      "tackle_for_loss_1_player_name",      "defteam",                "tackles_for_loss",  1.0),
    PlayerSlot("tackle_for_loss_2_player_id",      "tackle_for_loss_2_player_name",      "defteam",                "tackles_for_loss",  1.0),
    PlayerSlot("qb_hit_1_player_id",               "qb_hit_1_player_name",               "defteam",                "qb_hits",           1.0),
    PlayerSlot("qb_hit_2_player_id",               "qb_hit_2_player_name",               "defteam",                "qb_hits",           1.0),
    PlayerSlot("sack_player_id",                   "sack_player_name",                   "defteam",                "sacks",             1.0),
    PlayerSlot("half_sack_1_player_id",            "half_sack_1_player_name",            "defteam",                "sacks",             0.5),
    PlayerSlot("half_sack_2_player_id",            "half_sack_2_player_name",            "defteam",                "sacks",             0.5),
    PlayerSlot("interception_player_id",           "interception_player_name",           "defteam",                "def_interceptions", 1.0),
    PlayerSlot("pass_defense_1_player_id",         "pass_defense_1_player_name",         "defteam",                "pass_breakups",     1.0),
    PlayerSlot("pass_defense_2_player_id",         "pass_defense_2_player_name",         "defteam",                "pass_breakups",     1.0),
    PlayerSlot("forced_fumble_player_1_player_id", "forced_fumble_player_1_player_name", "defteam",                "forced_fumbles",    1.0),
    PlayerSlot("forced_fumble_player_2_player_id", "forced_fumble_player_2_player_name", "defteam",                "forced_fumbles",    1.0),
    PlayerSlot("fumble_recovery_1_player_id",      "fumble_recovery_1_player_name",      "fumble_recovery_1_team", "fumble_recoveries", 1.0),
    PlayerSlot("fumble_recovery_2_player_id",      "fumble_recovery_2_player_name",      "fumble_recovery_2_team", "fumble_recoveries", 1.0),
]


def sql_sum(col, alias, available):
    if col in available:
        return f"SUM({col}) AS {alias}"
    return f"CAST(0 AS DOUBLE) AS {alias}"


def extract_slot(plays, slot, available):
    if slot.id_col not in available:
        return None

    mask = plays[slot.id_col].notna()
    if not mask.any():
        return None

    sub = plays[mask]

    if slot.team_col in available:
        team = sub[slot.team_col]
    else:
        team = sub["posteam"] if "posteam" in available else pd.Series(["UNKNOWN"] * len(sub), index=sub.index)

    name   = sub[slot.name_col] if slot.name_col in available else pd.Series([None] * len(sub), index=sub.index)
    week   = sub["week"]        if "week"        in available else pd.Series([None] * len(sub), index=sub.index)
    season = sub["season"]      if "season"      in available else pd.Series([None] * len(sub), index=sub.index)

    return pd.DataFrame({
        "game_id":     sub["game_id"],
        "season":      season,
        "week":        week,
        "team":        team,
        "player_id":   sub[slot.id_col],
        "player_name": name,
        slot.stat:     slot.weight,
    })


def _season_filter(available: set, seasons: list[int]) -> str:
    if "season" not in available or not seasons:
        return ""
    return f"AND season IN ({', '.join(str(s) for s in seasons)})"


def build_passing_stats(conn, available, seasons):
    week_expr   = "week"   if "week"   in available else "NULL::INTEGER"
    season_expr = "season" if "season" in available else "NULL::INTEGER"
    sf = _season_filter(available, seasons)
    # Exclude 2-pt conversion plays (they inflate attempts/completions/yards and have no TD credit to the passer)
    two_pt = "AND COALESCE(two_point_attempt, 0) = 0" if "two_point_attempt" in available else ""
    sql = f"""
        SELECT
            game_id,
            passer_player_id                                                                             AS player_id,
            passer_player_name                                                                           AS player_name,
            posteam                                                                                      AS team,
            {season_expr}                                                                                AS season,
            {week_expr}                                                                                  AS week,
            COUNT(*) FILTER (WHERE pass_attempt = 1 AND COALESCE(sack, 0) = 0)                          AS attempts,
            SUM(complete_pass) FILTER (WHERE COALESCE(sack, 0) = 0)                                     AS completions,
            {sql_sum('passing_yards', 'pass_yards', available)},
            COUNT(*) FILTER (WHERE touchdown = 1 AND pass_attempt = 1 AND COALESCE(interception, 0) = 0) AS pass_tds,
            COUNT(*) FILTER (WHERE interception = 1)                                                    AS interceptions_thrown,
            COUNT(*) FILTER (WHERE sack = 1)                                                            AS sacks_taken,
            SUM(CASE WHEN pass_attempt = 1 OR COALESCE(sack, 0) = 1 THEN epa ELSE 0 END)               AS pass_epa
        FROM plays
        WHERE passer_player_id IS NOT NULL {two_pt} {sf}
        GROUP BY game_id, passer_player_id, passer_player_name, posteam, {season_expr}, {week_expr}
    """
    return conn.execute(sql).df()


def build_receiving_stats(conn, available, seasons):
    week_expr   = "week"   if "week"   in available else "NULL::INTEGER"
    season_expr = "season" if "season" in available else "NULL::INTEGER"
    sf = _season_filter(available, seasons)
    two_pt = "AND COALESCE(two_point_attempt, 0) = 0" if "two_point_attempt" in available else ""
    sql = f"""
        SELECT
            game_id,
            receiver_player_id                                            AS player_id,
            receiver_player_name                                          AS player_name,
            posteam                                                       AS team,
            {season_expr}                                                 AS season,
            {week_expr}                                                   AS week,
            COUNT(*) FILTER (WHERE pass_attempt = 1)                     AS targets,
            SUM(complete_pass)                                            AS receptions,
            {sql_sum('receiving_yards',  'rec_yards',  available)},
            COUNT(*) FILTER (WHERE touchdown = 1 AND pass_attempt = 1 AND COALESCE(interception, 0) = 0) AS rec_tds,
            {sql_sum('air_yards',        'air_yards',  available)},
            {sql_sum('yards_after_catch','yac',        available)},
            SUM(CASE WHEN pass_attempt = 1 THEN epa ELSE 0 END)          AS rec_epa
        FROM plays
        WHERE receiver_player_id IS NOT NULL {two_pt} {sf}
        GROUP BY game_id, receiver_player_id, receiver_player_name, posteam, {season_expr}, {week_expr}
    """
    return conn.execute(sql).df()


def build_rushing_stats(conn, available, seasons):
    week_expr   = "week"   if "week"   in available else "NULL::INTEGER"
    season_expr = "season" if "season" in available else "NULL::INTEGER"
    sf = _season_filter(available, seasons)
    two_pt = "AND COALESCE(two_point_attempt, 0) = 0" if "two_point_attempt" in available else ""
    sql = f"""
        SELECT
            game_id,
            rusher_player_id                                             AS player_id,
            rusher_player_name                                           AS player_name,
            posteam                                                      AS team,
            {season_expr}                                                AS season,
            {week_expr}                                                  AS week,
            COUNT(*)                                                     AS carries,
            {sql_sum('rushing_yards', 'rush_yards', available)},
            COUNT(*) FILTER (WHERE touchdown = 1 AND rush_attempt = 1)  AS rush_tds,
            SUM(CASE WHEN rush_attempt = 1 THEN epa ELSE 0 END)         AS rush_epa
        FROM plays
        WHERE rusher_player_id IS NOT NULL AND rush_attempt = 1 {two_pt} {sf}
        GROUP BY game_id, rusher_player_id, rusher_player_name, posteam, {season_expr}, {week_expr}
    """
    return conn.execute(sql).df()


def build_slot_stats(plays, slots):
    available = set(plays.columns)
    all_stat_names = {slot.stat for slot in slots}

    frames = [extract_slot(plays, slot, available) for slot in slots]
    frames = [f for f in frames if f is not None]
    if not frames:
        return pd.DataFrame()

    long = pd.concat(frames, ignore_index=True)

    for stat in all_stat_names:
        if stat not in long.columns:
            long[stat] = 0.0
        else:
            long[stat] = long[stat].fillna(0.0)

    agg_rules = {stat: "sum" for stat in all_stat_names}
    agg_rules["player_name"] = "first"

    return (
        long
        .groupby(["game_id", "player_id", "team", "season", "week"])
        .agg(agg_rules)
        .reset_index()
    )


def build_kicker_stats(plays):
    available = set(plays.columns)
    if "kicker_player_id" not in available:
        return pd.DataFrame()

    sub = plays[plays["kicker_player_id"].notna()].copy()
    if sub.empty:
        return pd.DataFrame()

    def flag(col, condition):
        if col in available:
            return condition.astype(float)
        return pd.Series(0.0, index=sub.index)

    frame = pd.DataFrame({
        "game_id":     sub["game_id"],
        "season":      sub["season"]           if "season"           in available else None,
        "week":        sub["week"]             if "week"             in available else None,
        "team":        sub["posteam"],
        "player_id":   sub["kicker_player_id"],
        "player_name": sub["kicker_player_name"] if "kicker_player_name" in available else None,
        "fg_att":      flag("field_goal_attempt", sub["field_goal_attempt"] == 1),
        "fg_made":     flag("field_goal_result",  sub["field_goal_result"]  == "made"),
        "xp_att":      flag("extra_point_attempt", sub["extra_point_attempt"] == 1),
        "xp_made":     flag("extra_point_result",  sub["extra_point_result"]  == "good"),
    })

    agg_rules = {"player_name": "first", "fg_att": "sum", "fg_made": "sum", "xp_att": "sum", "xp_made": "sum"}
    return frame.groupby(["game_id", "player_id", "team", "season", "week"]).agg(agg_rules).reset_index()


def build_punter_stats(plays):
    available = set(plays.columns)
    if "punter_player_id" not in available:
        return pd.DataFrame()

    sub = plays[plays["punter_player_id"].notna()].copy()
    if sub.empty:
        return pd.DataFrame()

    frame = pd.DataFrame({
        "game_id":     sub["game_id"],
        "season":      sub["season"]            if "season"            in available else None,
        "week":        sub["week"]              if "week"              in available else None,
        "team":        sub["posteam"],
        "player_id":   sub["punter_player_id"],
        "player_name": sub["punter_player_name"] if "punter_player_name" in available else None,
        "punts":       1.0,
        "punt_yards":  sub["kick_distance"]     if "kick_distance"     in available else 0.0,
    })

    agg_rules = {"player_name": "first", "punts": "sum", "punt_yards": "sum"}
    return frame.groupby(["game_id", "player_id", "team", "season", "week"]).agg(agg_rules).reset_index()


def build_returner_stats(plays):
    available = set(plays.columns)
    yards_col = next((c for c in ["return_yards", "yards_gained"] if c in available), None)

    result_frames = []

    configs = [
        ("kick_returner_player_id", "kick_returner_player_name", "kickoff",
         "kick_returns", "kick_return_yards", "kick_return_tds"),
        ("punt_returner_player_id", "punt_returner_player_name", "punt",
         "punt_returns", "punt_return_yards", "punt_return_tds"),
    ]

    for id_col, name_col, play_type_val, ret_stat, yds_stat, td_stat in configs:
        if id_col not in available:
            continue

        mask = plays[id_col].notna()
        if "play_type" in available:
            mask = mask & (plays["play_type"] == play_type_val)

        sub = plays[mask]
        if sub.empty:
            continue

        frame = pd.DataFrame({
            "game_id":     sub["game_id"],
            "season":      sub["season"] if "season" in available else None,
            "week":        sub["week"]   if "week"   in available else None,
            "team":        sub["posteam"],
            "player_id":   sub[id_col],
            "player_name": sub[name_col] if name_col in available else None,
            ret_stat:      1.0,
            yds_stat:      sub[yards_col].fillna(0) if yards_col else 0.0,
            td_stat:       (sub["touchdown"] == 1).astype(float) if "touchdown" in available else 0.0,
        })

        agg_rules = {"player_name": "first", ret_stat: "sum", yds_stat: "sum", td_stat: "sum"}
        result_frames.append(
            frame.groupby(["game_id", "player_id", "team", "season", "week"]).agg(agg_rules).reset_index()
        )

    return merge_all_stats(*result_frames) if result_frames else pd.DataFrame()
