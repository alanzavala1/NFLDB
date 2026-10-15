"""Classify expected missing optional feed schema, without hiding query/storage bugs."""
import re

import duckdb

# These are source/derived relations the application deliberately treats as
# unavailable in a cold or older snapshot. An unknown relation name is a bug.
OPTIONAL_DATA_TABLES = frozenset({
    'rosters', 'plays', 'schedules', 'snap_counts', 'id_map', 'player_game_stats',
    'weekly_player_stats',
    'ngs_passing', 'ngs_rushing', 'ngs_receiving', 'draft_picks',
    'combine_data', 'injuries', 'player_awards', 'depth_charts', 'ftn_charting',
    'player_game_ratings', 'team_game_ol_grades', 'team_power_rankings',
    'player_splits', 'defense_splits', 'team_splits', 'team_season_analytics',
    'player_career_summary', 'player_comparables',
})

# Source fields used by optional feed queries or legacy snapshot builders.
# Adding an optional field requires naming it here: misspelled/new unknown
# columns must not quietly turn a programming mistake into an empty response.
OPTIONAL_SOURCE_COLUMNS = frozenset('''
season week game_id game_type season_type gameday gametime team player player_id
player_name full_name gsis_id player_gsis_id pfr_id pfr_player_id pfr_player_id
position jersey_number headshot_url football_name dt pos_grp pos_abb pos_rank
offense_snaps defense_snaps st_snaps offense_pct defense_pct st_pct
report_primary_injury report_secondary_injury report_status practice_primary_injury
practice_status award round pick college age probowls allpro car_av w_av games
draft_year draft_round draft_ovr school pos ht wt forty bench vertical broad_jump cone shuttle
avg_time_to_throw avg_intended_air_yards avg_completed_air_yards
completion_percentage_above_expectation aggressiveness expected_completion_percentage
passer_rating rush_yards_over_expected rush_yards_over_expected_per_att efficiency
avg_time_to_los percent_attempts_gte_eight_defenders avg_separation avg_cushion
avg_yac avg_yac_above_expectation catch_percentage percent_share_of_intended_air_yards
posteam defteam qtr time desc game_seconds_remaining total_away_score total_home_score
home_wp touchdown td_team td_player_id interception fumble fumble_lost safety sp
extra_point_result two_point_conv_result field_goal_attempt field_goal_result kick_distance
pass_attempt complete_pass incomplete_pass rush_attempt sack down yardline_100 yards_gained epa qb_epa
success cpoe air_wpa yac_wpa wpa first_down third_down_converted third_down_failed
fourth_down_converted fourth_down_failed penalty penalty_team penalty_player_id
penalty_type penalty_yards pass_touchdown rush_touchdown first_down_pass first_down_rush
passing_yards rushing_yards receiving_yards return_touchdown return_yards
passer_player_id rusher_player_id receiver_player_id kicker_player_id kicker_player_name
punter_player_id punt_attempt touchback punt_inside_twenty punt_blocked
sack_player_id interception_player_id solo_tackle_1_player_id solo_tackle_2_player_id
assist_tackle_1_player_id assist_tackle_2_player_id assist_tackle_3_player_id assist_tackle_4_player_id
tackle_for_loss_1_player_id tackle_for_loss_2_player_id pass_defense_1_player_id pass_defense_2_player_id
qb_hit forced_fumble_player_1_player_id forced_fumble_player_2_player_id fumble_recovery_1_player_id
fumble_recovery_2_player_id qb_kneel qb_spike two_point_attempt pass_location pass_length
run_location run_gap shotgun no_huddle ydstogo play_type drive roof surface
attempts completions pass_yards pass_tds interceptions_thrown sacks_taken pass_epa
targets receptions rec_yards rec_tds air_yards yac rec_epa carries rush_yards rush_tds rush_epa
solo_tackles assist_tackles tackles_for_loss sacks qb_hits def_interceptions pass_breakups
forced_fumbles fumble_recoveries fg_att fg_made xp_att xp_made punts punt_yards
punt_returns punt_return_yards punt_return_tds away_team home_team
'''.split())


def is_missing_table_error(error: Exception, table: str) -> bool:
    """An absent write target may be created; an absent view dependency may not."""
    if not isinstance(error, duckdb.CatalogException):
        return False
    match = re.search(r'Table with name (.+?) does not exist', str(error))
    return bool(match and match.group(1).strip('"').lower() == table.lower())


def is_missing_data_error(error: Exception) -> bool:
    """Only absent tables/source columns qualify for an optional-data fallback.

    DuckDB distinguishes these from parser, connection, I/O, type and constraint
    errors. Missing functions or invalid table/CTE aliases are not data gaps.
    Required queries must still propagate these errors; this helper is only for
    callers whose contract explicitly allows unavailable data.
    """
    message = str(error)
    if isinstance(error, duckdb.CatalogException):
        match = re.search(r'Table with name (.+?) does not exist', message)
        return bool(match and match.group(1).strip('"').lower() in OPTIONAL_DATA_TABLES)
    if isinstance(error, duckdb.BinderException):
        match = re.search(r'Referenced column "([^"]+)" not found in FROM clause', message)
        if not match:
            match = re.search(r'Table .+ does not have a column named "([^"]+)"', message)
        return bool(match and match.group(1).lower() in OPTIONAL_SOURCE_COLUMNS)
    return False
