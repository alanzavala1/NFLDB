"""Read-only schema, season coverage and statistical checks for prepared data."""
import importlib

import duckdb

from pipeline.reconciliation import impossible_rates, receiving_total_checks, season_checks


class SnapshotValidationError(RuntimeError):
    pass


BUILDERS = (
    'team_analytics_builder', 'power_rankings_builder', 'game_ratings_builder',
    'ol_grades_builder', 'splits_builder', 'def_splits_builder', 'team_splits_builder',
)
SEASONAL_TABLES = (
    'schedules', 'rosters', 'weekly_player_stats', 'player_game_stats',
    'team_season_analytics', 'team_power_rankings', 'player_game_ratings',
    'team_game_ol_grades', 'team_splits',
)


def _require(condition, message):
    if not condition:
        raise SnapshotValidationError(message)


def _check_schema(conn):
    # Use the builders' own DDL as the contract; never create/repair candidate
    # tables during validation. The scratch connection is purely in-memory.
    expected = duckdb.connect(':memory:')
    try:
        for module in BUILDERS:
            expected.execute(importlib.import_module(module)._TABLE_DDL)
        import comparables_builder
        expected.execute(comparables_builder._SUMMARY_DDL)
        expected.execute(comparables_builder._COMPARABLES_DDL)
        tables = {r[0] for r in conn.execute('SHOW TABLES').fetchall()}
        for (table,) in expected.execute('SHOW TABLES').fetchall():
            _require(table in tables, f'{table}: missing prepared table')
            actual = {r[1]: r[2] for r in conn.execute(f"PRAGMA table_info('{table}')").fetchall()}
            columns = expected.execute(f"PRAGMA table_info('{table}')").fetchall()
            for _, name, kind, _, _, _ in columns:
                _require(actual.get(name) == kind, f'{table}.{name}: expected {kind}, got {actual.get(name)}')
            keys = [r[1] for r in columns if r[5]]
            key_sql = ', '.join(f'"{k}"' for k in keys)
            nulls = ' OR '.join(f'"{k}" IS NULL' for k in keys)
            _require(conn.execute(f'SELECT COUNT(*) FROM {table} WHERE {nulls}').fetchone()[0] == 0,
                     f'{table}: null lookup key')
            duplicates = conn.execute(
                f'SELECT COUNT(*) FROM (SELECT {key_sql} FROM {table} GROUP BY {key_sql} HAVING COUNT(*) > 1)'
            ).fetchone()[0]
            _require(duplicates == 0, f'{table}: duplicate lookup keys')
    finally:
        expected.close()


def validate_snapshot(conn, *, receiving_inputs=None, log=lambda message: None):
    """Validate every loaded regular season, including historical and newest data.

    Low-volume player splits and career comparables may legitimately be empty.
    This gate does not assert freshness or completeness of optional vendor feeds.
    """
    tables = {row[0] for row in conn.execute('SHOW TABLES').fetchall()}
    _require('receiving_preview_preparation' not in tables
             and not any(table.startswith('receiving_') and table.endswith('_preview') for table in tables),
             'Receiving-only preview is not a publishable snapshot')
    official = bool(tables & {'receiving_build_preparation', 'receiving_whole_reference', 'receiving_season_totals'})
    guard = 'Official receiving integration awaits coverage-aware API/UI and complete release validation'
    _require(not official or receiving_inputs is not None,
             guard + '; provide captured --core-inputs to run the full integration checks')
    _require(official or receiving_inputs is None, 'Captured receiving inputs require official receiving preparation records')
    _check_schema(conn)
    if official:
        from pipeline.receiving_validation import validate_receiving
        from pipeline.receiving_inputs import verify_stored_ftn
        from pipeline.snapshots import check_preparation, CandidateError
        from pipeline.source_results import SourceError
        try:
            check_preparation(conn)
            receiving = validate_receiving(conn, receiving_inputs, log=log)
            verify_stored_ftn(conn, receiving_inputs, receiving['played_seasons'])
        except (CandidateError, SourceError, KeyError, TypeError, ValueError) as error:
            raise SnapshotValidationError(f'Official snapshot source check failed: {error}') from error
    seasons = [r[0] for r in conn.execute(
        "SELECT DISTINCT season FROM plays WHERE season_type = 'REG' ORDER BY season"
    ).fetchall()]
    _require(bool(seasons), 'No loaded regular-season plays to validate')
    coverage = {}
    for table in (*SEASONAL_TABLES, 'player_splits', 'defense_splits'):
        coverage[table] = dict(conn.execute(f'SELECT season, COUNT(*) FROM {table} GROUP BY season').fetchall())
    for season in seasons:
        for table in SEASONAL_TABLES:
            _require(coverage[table].get(season, 0) > 0, f'{table}[{season}]: no prepared rows')
        # Match the builders' admission thresholds; early-season players may
        # have too few plays/events for either player splits table yet.
        import splits_builder
        available = {r[0] for r in conn.execute('DESCRIBE plays').fetchall()}
        for category in ('passing', 'rushing', 'receiving'):
            if official and category == 'receiving':
                continue  # Exact fresh-source admission is already checked by replay.
            eligibility = splits_builder.qualification_ctes(category, season, available)
            qualifying = {r[0] for r in conn.execute(f'{eligibility} SELECT player_id FROM qualified').fetchall()}
            stored = {r[0] for r in conn.execute('''SELECT DISTINCT player_id FROM player_splits
                WHERE season = ? AND category = ?''', [season, category]).fetchall()}
            _require(not qualifying - stored,
                     f'player_splits[{season}, {category}]: qualifying players missing from prepared rows')
        import def_splits_builder
        qualifying_defenders = {r[0] for r in conn.execute(f'''
            SELECT player_id FROM ({def_splits_builder._events_union(int(season))})
            GROUP BY player_id HAVING COUNT(*) >= {def_splits_builder._MIN_EVENTS}''').fetchall()}
        stored_defenders = {r[0] for r in conn.execute(
            'SELECT DISTINCT player_id FROM defense_splits WHERE season = ?', [season]).fetchall()}
        _require(not qualifying_defenders - stored_defenders,
                 f'defense_splits[{season}]: qualifying defenders missing from prepared rows')

    from database import _INDEXES
    indexes = set(conn.execute('SELECT table_name, index_name FROM duckdb_indexes()').fetchall())
    tables = {r[0] for r in conn.execute('SHOW TABLES').fetchall()}
    for table, column in _INDEXES:
        if table in tables:
            _require((table, f'idx_{table}_{column}') in indexes, f'{table}.{column}: missing lookup index')
    _require(conn.execute('SELECT COUNT(*) FROM player_awards').fetchone()[0] > 0, 'player_awards: no prepared rows')
    _require(impossible_rates(conn) == 0, 'player_splits: impossible rates or nonfinite EPA')
    for table, column in (('player_game_ratings', 'rating'), ('team_game_ol_grades', 'grade')):
        invalid = conn.execute(f'''SELECT COUNT(*) FROM {table} WHERE {column} IS NOT NULL
            AND (NOT isfinite({column}) OR {column} < 3 OR {column} > 10)''').fetchone()[0]
        _require(invalid == 0, f'{table}: invalid {column}')

    if official:
        from pipeline.analytics_coverage import check_analytics_coverage
        check_analytics_coverage(conn, seasons)
    reconciliation, failures = {}, []
    for season in seasons:
        checks = {**receiving_total_checks(conn, season),
                  **season_checks(conn, season, official_receiving=official)}
        for name, (mismatches, allowed) in checks.items():
            if mismatches > allowed:
                failures.append(f'{name}[{season}]: {mismatches} mismatches (allowed {allowed})')
        reconciliation[season] = checks
        log(f'Snapshot[{season}]: ' + ', '.join(f'{key}={value[0]}/{value[1]}' for key, value in checks.items()))
    _require(not failures, '\n'.join(failures))
    # Keep publication blocked while the complete real-history proof and the
    # remaining legacy receiving consumers are audited. Inputs enable diagnosis,
    # not an opt-out from this release boundary.
    _require(not official, guard)
    return {'played_seasons': seasons, 'coverage': coverage, 'reconciliation': reconciliation,
            'allowed_empty': ['player splits below admission thresholds',
                              'career comparables below volume/pool thresholds',
                              'optional vendor feeds with recorded gaps']}
