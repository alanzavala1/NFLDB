"""Player data functions; HTTP-independent selection and assembly."""
from sql_helpers import DEPTH_CHART_SEL, safe_query


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
    """Current depth-chart slot from the latest vendor snapshot (the feed is
    daily snapshots — see DEPTH_CHART_SEL — with no season/week history).
    A player holding several slots (e.g. WR + kick returner) surfaces the
    non-special-teams one, then the best rank. UI shows it as a badge
    (e.g. 'Starting QB')."""
    rows = safe_query(f"""
        SELECT {DEPTH_CHART_SEL}
        FROM depth_charts
        WHERE gsis_id = ? AND dt = (SELECT MAX(dt) FROM depth_charts)
        ORDER BY (pos_grp = 'Special Teams'), pos_rank
        LIMIT 1
    """, [player_id])
    return rows[0] if rows else None
