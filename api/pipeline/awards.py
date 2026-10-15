"""Prepare static player awards with the existing roster identity join."""


def load_player_awards(conn, log=print) -> None:
    """Build `player_awards` from the static seed in awards_seed.py.

    Joins each award row to its winning player's gsis_id via the rosters
    table (matched by player_name + the award's season). Players who
    can't be matched are still stored — they just won't link from
    PlayerPage. Re-running ingest fully replaces the table.
    """
    import awards_seed
    import pandas as pd

    rows = awards_seed.all_rows()
    if not rows:
        log("    awards seed is empty, leaving table unchanged")
        return

    seed = pd.DataFrame(rows)
    conn.register("awards_seed_df", seed)

    # Join to rosters on (player_name, season) to recover gsis_id. Players
    # who appear in awards but not in rosters (e.g. coaches, or names that
    # don't match exactly) get NULL gsis_id and will simply not surface on
    # PlayerPage — but the row is still there for audit / a future fix.
    conn.execute("DROP TABLE IF EXISTS player_awards")
    conn.execute("""
        CREATE TABLE player_awards AS
        SELECT
            s.season,
            s.award,
            s.player          AS player_name,
            s.team,
            s.pos             AS position,
            r.player_id       AS gsis_id
        FROM awards_seed_df s
        LEFT JOIN (
            SELECT DISTINCT player_id, player_name, season
            FROM rosters
        ) r
          ON r.player_name = s.player
         AND r.season      = s.season
    """)

    total = conn.execute("SELECT COUNT(*) FROM player_awards").fetchone()[0]
    matched = conn.execute(
        "SELECT COUNT(*) FROM player_awards WHERE gsis_id IS NOT NULL"
    ).fetchone()[0]
    log(f"    player_awards: {total} rows, {matched} matched to a gsis_id "
        f"({100 * matched // max(total, 1)}%)")
