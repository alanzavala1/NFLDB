"""Pure vendor-frame normalization; no downloading or database writes."""
import pandas as pd

from config import RELOCATIONS


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


def normalize_relocated_teams(df: pd.DataFrame) -> pd.DataFrame:
    """Map modern franchise abbreviations back to era ones (see config.RELOCATIONS).

    Play-by-play and weekly sources say 'LV' even for a 2005 Raiders play;
    schedules and rosters say 'OAK'. player_game_stats joins against both, so
    its team column must use the era abbreviation.
    """
    if df.empty or "team" not in df.columns or "season" not in df.columns:
        return df
    for modern, era, last_era_season in RELOCATIONS:
        mask = (df["team"] == modern) & (df["season"] <= last_era_season)
        df.loc[mask, "team"] = era
    return df


def merge_all_stats(*stat_frames):
    frames = [f for f in stat_frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()

    # Exclude 'team' from merge keys: different stat sources use posteam vs defteam,
    # which creates duplicate rows for the same player+game with different team values.
    # Instead we coalesce team from the primary (leftmost) source after each join.
    keys = ["game_id", "player_id", "season", "week"]
    merged = frames[0]

    for frame in frames[1:]:
        merged = merged.merge(frame, on=keys, how="outer", suffixes=("", "_r"))
        if "team_r" in merged.columns:
            merged["team"] = merged["team"].combine_first(merged["team_r"])
            merged.drop(columns=["team_r"], inplace=True)
        if "player_name_r" in merged.columns:
            merged["player_name"] = merged["player_name"].combine_first(merged["player_name_r"])
            merged.drop(columns=["player_name_r"], inplace=True)

    non_stat = keys + ["team", "player_name"]
    stat_cols = [c for c in merged.columns if c not in non_stat]
    merged[stat_cols] = merged[stat_cols].fillna(0)

    return merged
