"""One-off: rebuild player_splits with the corrected attempt logic and verify
that pbp attempt counts now reconcile with the official game log.

Run from the api/ dir with the project venv, with the API server stopped
(DuckDB is single-writer):  venv\\Scripts\\python.exe rematerialize_splits.py
"""
import splits_builder
from database import get_connection, query_to_dict


def main() -> None:
    conn = get_connection()
    seasons = [r[0] for r in conn.execute(
        "SELECT DISTINCT season FROM player_splits ORDER BY season"
    ).fetchall()]
    if not seasons:
        seasons = [r[0] for r in conn.execute(
            "SELECT DISTINCT season FROM plays ORDER BY season"
        ).fetchall()]
    print(f"Re-materializing player_splits for {len(seasons)} seasons: {seasons[0]}–{seasons[-1]}")
    total = 0
    for s in seasons:
        total += splits_builder.materialize(s)
    print(f"  wrote {total:,} rows")

    # Verify league-wide: the sum of each player's per-down splits (the "overall"
    # the page shows) must equal official weekly_player_stats, for every
    # qualifying player. Counts must be exact; tiny yardage diffs are inherent
    # nflfastR lateral-credit quirks.
    checks = [
        ("passing",   "att",   "attempts",       100),
        ("passing",   "yards", "passing_yards",  1000),
        ("rushing",   "att",   "carries",        50),
        ("rushing",   "yards", "rushing_yards",  300),
        ("receiving", "att",   "targets",        50),
        ("receiving", "yards", "receiving_yards",300),
    ]
    print()
    for cat, col, off_col, vol in checks:
        rows = query_to_dict(f"""
            WITH s AS (
                SELECT player_id, SUM({col}) v FROM player_splits
                WHERE category='{cat}' AND split_dim='down' AND season=2023
                GROUP BY player_id
            ), o AS (
                SELECT player_id, SUM({off_col}) v FROM weekly_player_stats
                WHERE season=2023 AND season_type='REG' GROUP BY player_id
            )
            SELECT COUNT(*) checked,
                   COUNT(*) FILTER (WHERE COALESCE(s.v,0) <> o.v) mism
            FROM o LEFT JOIN s USING(player_id)
            WHERE o.v >= {vol}
        """)
        r = rows[0]
        tag = "OK" if r['mism'] == 0 else f"*** {r['mism']} MISMATCHED ***"
        print(f"  2023 {cat:10} {col:6} vs official {off_col:16}: {r['checked']:3} checked  {tag}")


if __name__ == "__main__":
    main()
