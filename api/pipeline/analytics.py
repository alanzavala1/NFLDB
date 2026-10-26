"""Offline preparation of analytics tables and persisted lookup indexes.

Source loading and player_game_stats construction happen before this step.
This orchestrates existing builders; it does not validate snapshot completeness.
"""


def prepare_analytics(seasons: list[int], log=print, *, receiving_inputs=None) -> None:
    """Rebuild seasonal tables and globally calibrated analytics in dependency order."""
    # Materialize team-analytics so /team-analytics serves a precomputed
    # SELECT instead of running a 150-line CTE per request.
    log("\nMaterializing team analytics...")
    import team_analytics_builder
    for season in seasons:
        n = team_analytics_builder.materialize(season)
        log(f"  team_season_analytics[{season}]: {n} rows")

    # Materialize weekly EPA power rankings for the ingested seasons.
    log("\nMaterializing team power rankings...")
    import power_rankings_builder
    for season in seasons:
        n = power_rankings_builder.materialize(season)
        log(f"  team_power_rankings[{season}]: {n} rows")

    # Materialize per-game player ratings. Ratings are percentile-calibrated
    # across every loaded season, so this is a global rebuild.
    log("\nMaterializing player game ratings...")
    import game_ratings_builder
    n = game_ratings_builder.materialize()
    log(f"  player_game_ratings: {n} rows")

    # Materialize O-line unit grades — same global percentile calibration.
    log("\nMaterializing offensive line unit grades...")
    import ol_grades_builder
    n = ol_grades_builder.materialize()
    log(f"  team_game_ol_grades: {n} rows")

    # Materialize player splits — the player's stat line conditioned on each
    # situational dimension, precomputed per season.
    log("\nMaterializing player splits...")
    import splits_builder
    for season in seasons:
        options = {} if receiving_inputs is None else {"receiving_inputs": receiving_inputs}
        n = splits_builder.materialize(season, **options)
        log(f"  player_splits[{season}]: {n} rows")

    # Materialize defensive player splits — event line by situation.
    log("\nMaterializing defensive splits...")
    import def_splits_builder
    for season in seasons:
        n = def_splits_builder.materialize(season)
        log(f"  defense_splits[{season}]: {n} rows")

    # Materialize team splits — team offense/defense rate profile by situation.
    log("\nMaterializing team splits...")
    import team_splits_builder
    for season in seasons:
        n = team_splits_builder.materialize(season)
        log(f"  team_splits[{season}]: {n} rows")

    # Rebuild player comparables — career stats shifted with the new ingest,
    # so z-scores and neighbor rankings need to be recomputed across all
    # players. Done once per ingest batch (not per season) to amortize cost.
    log("\nRebuilding player comparables...")
    import comparables_builder
    summary_n, pairs_n = comparables_builder.materialize()
    log(f"  player_career_summary: {summary_n} players")
    log(f"  player_comparables:    {pairs_n} rows")

    # Recreate point-lookup indexes (tables rebuilt via CREATE TABLE AS drop them).
    import database
    database.ensure_indexes()

    log("\nDone.")
