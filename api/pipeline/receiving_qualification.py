"""Apply existing eligibility to the same fresh plays used by the R calculator."""
import hashlib

import duckdb
import numpy as np
import pandas as pd

from pipeline.snapshots import CandidateError


_FLAGS = ("complete_pass", "incomplete_pass", "interception", "two_point_attempt")
_KEYS = ["game_id", "play_id"]


def qualify_receiving_context(context: pd.DataFrame, season: int, context_sha256: str) -> tuple[list[str], dict]:
    """Validate a bound REG/nonconversion context, then reuse canonical SQL.

    This uses original-receiver attempt plays, as before, not official credit
    totals or availability of a split's optional context. An isolated in-memory
    connection prevents copied/stale plays from influencing player admission.
    """
    required = {*_KEYS, "season", "season_type", "receiver_player_id", *_FLAGS}
    if required - set(context.columns):
        raise CandidateError("Receiving qualification context missing required fields")
    if (context.empty or context[["season", "season_type"]].isna().any().any()
            or not context.season.eq(season).all() or not context.season_type.eq("REG").all()
            or context.two_point_attempt.eq(1).any()):
        raise CandidateError("Receiving qualification context has unexpected scope")
    if (context[_KEYS].isna().any().any() or context.duplicated(_KEYS).any()
            or not context.game_id.map(lambda value: isinstance(value, str) and bool(value.strip())).all()):
        raise CandidateError("Receiving qualification has missing/duplicate play identity")
    try:
        play_ids = pd.to_numeric(context.play_id, errors="raise").to_numpy(dtype=float)
    except (TypeError, ValueError) as error:
        raise CandidateError("Receiving qualification has invalid play IDs") from error
    if not np.isfinite(play_ids).all() or (play_ids < 0).any() or not (play_ids == np.trunc(play_ids)).all():
        raise CandidateError("Receiving qualification has invalid play IDs")
    if any(not context[field].dropna().isin([0, 1]).all() for field in _FLAGS):
        raise CandidateError("Receiving qualification has invalid attempt/conversion flags")
    if not context.receiver_player_id.dropna().map(
        lambda player: isinstance(player, str) and bool(player) and player == player.strip()
    ).astype(bool).all():
        raise CandidateError("Receiving qualification has invalid receiver identity")
    if not isinstance(context_sha256, str) or len(context_sha256) != 64 or any(
        value not in "0123456789abcdef" for value in context_sha256
    ):
        raise CandidateError("Receiving qualification requires a verified context SHA256")
    # The worker disables legacy config's schedule lookup before reaching here.
    from splits_builder import qualification_ctes
    sql = qualification_ctes("receiving", season, set(context.columns), minimal=True)
    with duckdb.connect(":memory:") as conn:
        conn.register("plays", context)
        admitted = conn.execute(sql + """ SELECT player_id, COUNT(*) AS qualifying_plays
            FROM base JOIN qualified USING (player_id) GROUP BY player_id ORDER BY player_id""").fetchall()
    players = [row[0] for row in admitted]
    return players, {"source": "bound fresh PBP context", "players": len(players),
                     "qualifying_plays": {player: count for player, count in admitted},
                     "source_revisions": {f"context-{season}.csv": context_sha256},
                     "sql_sha256": hashlib.sha256(sql.encode()).hexdigest()}
