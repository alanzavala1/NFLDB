"""Core table writes for offline preparation; no downloading or football formulas."""
import duckdb
import pandas as pd

from data_errors import is_missing_data_error, is_missing_table_error


def upsert_by_season(conn, table: str, df: pd.DataFrame, seasons: list[int], log=print, *, evolve_schema=False):
    """Create table if needed, replace data for the given seasons, then insert.

    Inserts only columns common to both the existing table and the new dataframe
    so season-to-season schema differences in nfl_data_py never wipe other seasons.
    Captured core plays explicitly opt into schema evolution and strict casts;
    missing columns and formerly numeric ID columns must not discard source values.
    """
    conn.register(f"{table}_df", df)

    try:
        existing_cols = [r[0] for r in conn.execute(f"DESCRIBE {table}").fetchall()]
    except Exception as error:
        if not is_missing_table_error(error, table):
            raise
        existing_cols = None

    if existing_cols is None:
        conn.execute(f"CREATE TABLE {table} AS SELECT * FROM {table}_df")
    else:
        if evolve_schema:
            # Explicit opt-in for captured core plays: their checked projection
            # must survive an older DB schema. Keep other feeds' existing policy.
            for name, kind, *_ in conn.execute(f'DESCRIBE SELECT * FROM {table}_df').fetchall():
                if name not in existing_cols:
                    quoted = name.replace('"', '""')
                    conn.execute(f'ALTER TABLE {table} ADD COLUMN "{quoted}" {kind}')
                    existing_cols.append(name)
            common = [name for name in existing_cols if name in df.columns]
            names = ', '.join('"' + name.replace('"', '""') + '"' for name in common)
            current = {row[0]: row[1] for row in conn.execute(f'DESCRIBE {table}').fetchall()}
            # DuckDB's union type rules preserve text IDs stored in formerly
            # all-NULL numeric columns, and widen numeric fields when needed.
            promoted = conn.execute(f'DESCRIBE SELECT {names} FROM {table} UNION ALL SELECT {names} FROM {table}_df').fetchall()
            for name, kind, *_ in promoted:
                if current[name] != kind:
                    quoted = name.replace('"', '""')
                    conn.execute(f'ALTER TABLE {table} ALTER COLUMN "{quoted}" TYPE {kind}')
        placeholders = ", ".join("?" * len(seasons))
        try:
            conn.execute(f"DELETE FROM {table} WHERE season IN ({placeholders})", seasons)
        except Exception as error:
            if not is_missing_data_error(error):
                raise
            pass  # no season column in very old tables — safe to skip

        col_types = {r[0]: r[1] for r in conn.execute(f"DESCRIBE {table}").fetchall()}
        common = [c for c in existing_cols if c in set(df.columns)]
        if common:
            cast = 'CAST' if evolve_schema else 'TRY_CAST'
            select_exprs = ", ".join(f'{cast}("{c}" AS {col_types[c]}) AS "{c}"' for c in common)
            col_list = ", ".join(f'"{c}"' for c in common)
            conn.execute(f"INSERT INTO {table} ({col_list}) SELECT {select_exprs} FROM {table}_df")
        else:
            conn.execute(f"DROP TABLE {table}")
            conn.execute(f"CREATE TABLE {table} AS SELECT * FROM {table}_df")

    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    log(f"  {table}: {count:,} rows total")


def replace_table(conn, table: str, df: pd.DataFrame, log=print) -> None:
    """Full-replace a table. For historical sources (draft picks, combine,
    id mapping) where the dataset is small and not partitioned by season."""
    if df is None or df.empty:
        log(f"    {table}: empty payload, leaving table unchanged")
        return
    conn.register(f"{table}_df", df)
    conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute(f"CREATE TABLE {table} AS SELECT * FROM {table}_df")
    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    log(f"    {table}: {count:,} rows")


def weekly_schema_is_legacy(conn) -> bool:
    """True if the stored table predates the stats_player rename.

    `recent_team` became `team`; its presence is the cheapest unambiguous marker.
    """
    try:
        cols = {r[0] for r in conn.execute("DESCRIBE weekly_player_stats").fetchall()}
    except Exception as error:
        if not is_missing_data_error(error):
            raise
        return False
    return bool(cols) and "team" not in cols


def store_weekly_stats(conn, weekly: pd.DataFrame, seasons: list[int], *, legacy=False, log=print):
    if legacy:
        conn.execute('DROP TABLE weekly_player_stats')
    upsert_by_season(conn, 'weekly_player_stats', weekly, seasons, log=log)
    stale = conn.execute(
        'DELETE FROM weekly_player_stats WHERE player_id IS NULL RETURNING 1'
    ).fetchall()
    if stale:
        log(f'  purged {len(stale)} stored rows with no player_id')
    log(f'  weekly_player_stats: {len(weekly):,} rows, seasons {seasons[0]}-{seasons[-1]}')


def store_player_game_stats(conn, frame: pd.DataFrame, seasons: list[int], log=print):
    """Create only an absent table; propagate every subsequent write failure."""
    conn.register('pgs_df', frame)
    try:
        conn.execute('SELECT 1 FROM player_game_stats LIMIT 1')
    except duckdb.CatalogException as error:
        if not is_missing_table_error(error, 'player_game_stats'):
            raise
        conn.execute('CREATE TABLE player_game_stats AS SELECT * FROM pgs_df')
    else:
        placeholders = ', '.join('?' * len(seasons))
        conn.execute(f'DELETE FROM player_game_stats WHERE season IN ({placeholders})', seasons)
        existing_cols = [r[0] for r in conn.execute('DESCRIBE player_game_stats').fetchall()]
        common = [c for c in existing_cols if c in set(frame.columns)]
        cols = ', '.join(f'"{c}"' for c in common)
        conn.execute(f'INSERT INTO player_game_stats ({cols}) SELECT {cols} FROM pgs_df')
    count = conn.execute('SELECT COUNT(*) FROM player_game_stats').fetchone()[0]
    log(f'  player_game_stats: {count:,} rows total')
