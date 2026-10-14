"""Pure vendor-frame normalization; no downloading or database writes."""
import pandas as pd


def normalize_ftn(frame: pd.DataFrame) -> pd.DataFrame:
    # Match nfl_data_py's float32 policy before restoring the play join's FLOAT.
    frame = frame.copy()
    floats = frame.select_dtypes(include=['float64']).columns
    frame[floats] = frame[floats].astype('float32')
    keep = ['season', 'nflverse_game_id', 'nflverse_play_id', 'is_play_action',
            'is_rpo', 'is_screen_pass', 'is_motion', 'is_qb_out_of_pocket',
            'n_blitzers', 'n_pass_rushers', 'n_defense_box']
    frame = frame[[c for c in keep if c in frame.columns]].rename(
        columns={'nflverse_game_id': 'game_id', 'nflverse_play_id': 'play_id'})
    frame['play_id'] = frame['play_id'].astype('float64')
    return frame


def latest_depth_snapshot(frame: pd.DataFrame) -> pd.DataFrame:
    return frame[frame['dt'] == frame['dt'].max()].copy()
