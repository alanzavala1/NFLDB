"""Selection boundaries used by lineup responses and player-chart role fallback."""
from copy import deepcopy

from services.game_players import (
    defense_personnel, lineup_players, offense_personnel, position_group, rotation_players,
)


def _row(player_id):
    return dict(player_id=player_id, team='BUF', player_name=player_id,
                position='WR', offense_snaps=10, defense_snaps=0, st_snaps=0,
                offense_pct=0.5, defense_pct=None, st_pct=None)


def test_starters_keep_team_volume_cap_ties_and_input_rows():
    rows = [dict(_row('rated'), offense_snaps=60, rating=8),
            dict(_row('z'), offense_snaps=60, rating=7),
            dict(_row('a'), offense_snaps=60, rating=7),
            dict(_row('unknown'), offense_snaps=60),
            dict(_row('low'), offense_snaps=59, rating=10)]
    rows += [_row(f'filler-{i}') for i in range(8)]
    rows += [dict(_row('other'), team='MIA', offense_snaps=99),
             dict(_row('zero'), offense_snaps=0)]
    before = deepcopy(rows)
    selected = lineup_players(rows, 'BUF', 'offense')
    assert len(selected) == 11
    assert [row['player_id'] for row in selected[:5]] == ['rated', 'z', 'a', 'unknown', 'low']
    assert rows == before
    assert selected[3]['rating'] is None and selected[3]['headshot_url'] is None
    assert all(row['team'] == 'BUF' and row['snaps'] > 0 for row in selected)


def test_rotation_excludes_starters_and_keeps_rated_first_with_maximum_unit_values():
    rows = [dict(_row('rated'), rating=5, offense_snaps=1, defense_snaps=3, st_snaps=2,
                 offense_pct=0.9, defense_pct=0.6, st_pct=0.1),
            dict(_row('unrated'), offense_snaps=100)]
    rows += [_row(f'other-{i}') for i in range(10)]
    rows += [_row('starter'), dict(_row(None), offense_snaps=80),
             dict(_row('wrong-team'), team='MIA'), dict(_row('zero'), offense_snaps=0)]
    before = deepcopy(rows)
    selected = rotation_players(rows, 'BUF', {'starter', None})
    assert len(selected) == 10
    assert selected[0]['player_id'] == 'rated'
    assert (selected[0]['snaps'], selected[0]['snap_pct']) == (3, 0.9)
    assert selected[1]['player_id'] == 'unrated'
    assert all(row['player_id'] not in {'starter', None, 'wrong-team', 'zero'} for row in selected)
    assert rows == before


def test_personnel_labels_keep_back_counts_and_defensive_packages():
    offense = [{'position': p} for p in ['QB', 'rb', 'FB', 'TE', 'WR', 'LT']]
    assert offense_personnel(offense) == '21 personnel'
    defense = [{'position': p} for p in ['CB', 'CB', 'NB', 'FS', 'SS', 'LB']]
    assert defense_personnel(defense) == 'Nickel'
    assert defense_personnel(defense + [{'position': 'DB'}]) == 'Dime'
    assert offense_personnel([]) is None and defense_personnel([]) is None


def test_missing_names_and_position_fallbacks_keep_nullable_projection():
    row = dict(_row('unknown'), player_name=None, position='hb', jersey_number=None,
               offense_snaps=4.0, scored_td=1)
    player = lineup_players([row], 'BUF', 'offense')[0]
    assert (player['player_name'], player['position_group'], player['snaps']) == ('Unknown', 'RB', 4)
    assert player['jersey_number'] is None and player['scored_td'] is True
    assert position_group(None) is None and position_group('NB') is None
