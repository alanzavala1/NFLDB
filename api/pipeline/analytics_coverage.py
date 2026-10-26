"""Read-only checks for games missing from dependent analytics."""
from pipeline.validation import SnapshotValidationError


def check_analytics_coverage(conn, seasons):
    """Require every supplied REG game, not merely one row per season.

    Missing upstream games remain in the receiving coverage report. This check
    prevents supplied games from disappearing during downstream preparation.
    """
    report = {}
    for year in seasons:
        supplied = {row[0] for row in conn.execute(
            "SELECT DISTINCT game_id FROM plays WHERE season=? AND season_type='REG'", [year]).fetchall()}
        counts = {"supplied_reg_games": len(supplied)}
        for table in ("player_game_stats", "player_game_ratings", "team_game_ol_grades"):
            actual = {row[0] for row in conn.execute(
                f"SELECT DISTINCT game_id FROM {table} WHERE season=?", [year]).fetchall()}
            missing = supplied - actual
            if missing:
                raise SnapshotValidationError(f"{table}[{year}]: missing supplied REG games: {sorted(missing)}")
            counts[table] = len(supplied & actual)
        report[year] = counts
    return report
