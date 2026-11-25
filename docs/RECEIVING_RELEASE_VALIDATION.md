# Receiving splits

Receiving splits use the pinned nflfastR calculator on filtered play-by-play.
Detailed player credits preserve catches, yards and touchdowns on lateral plays;
play context determines the situation before player selection.

## Calculation and eligibility

A source-bound core collection contains the play-by-play, weekly reference,
individual credits, context assignments and calculator exports. Preparation
verifies that the database uses those same inputs before storing split rows.
The existing admission threshold is 25 original-receiver attempt plays per season,
not 25 official targets. Players below that threshold remain in source checks.

Whole-season, classified and excluded production are tracked separately. A play
without a usable context label remains in the whole reference rather than being
assigned to a guessed bucket. Exclusions from different views can overlap and
must not be added together.

## Views and definitions

| View | Definition |
|---|---|
| `down` | Downs 1–4 |
| `quarter` | Quarters 1–4; later periods grouped as OT |
| `home_away` | Designated game side, including neutral-site games |
| `shotgun`, `no_huddle` | Recorded flags; missing is not false |
| `field_zone` | Own territory, opponent territory and red zone |
| `game_script` | Leading, tied or trailing before the play |
| `game_state` | Win probability 0.05–0.95 inclusive is competitive |
| `roof`, `surface` | Reviewed source labels; unknown labels remain unclassified |
| `opponent` | Season-sensitive franchise code |
| `opp_division` | Current franchise division, including older seasons |
| `target_depth`, `target_direction` | Original pass depth/direction, shared by credited lateral recipients |
| `pressure` | Recorded QB hit versus no hit; unavailable before 2006, not complete pressure charting |
| `play_action` | FTN true/false, distinct from uncharted |
| `blitz` | FTN pass rushers: 1–4 standard, 5–11 blitz; not the `n_blitzers` field |

FTN starts in 2022 and joins by season, game and play. Roof aliases group
closed/dome and open/outdoors. Surface uses the reviewed grass/turf map, including
its legacy treatment of hybrid labels. See `pipeline/receiving_dimensions.py`
and `receiving_context_rules.py` for the exact mappings.

Targets are unavailable in 2003–2008, yards after catch (YAC) before 2006 and air yards before 2009.
Supported receptions, yards and touchdowns remain usable. Target-based rates
require matching target-role populations; a lateral recipient's yardage does
not create a target or reception. See [methodology](../api/docs/METHODOLOGY.md).

## Validation

From `api/`, validate an existing closed database against its matching captures:

```sh
uv run --locked python -m jobs.validate_receiving \
  --database data/candidate.duckdb --core-inputs data/core-inputs
```

The check replays every loaded regular season, compares whole and bucket counts,
verifies qualification, metadata, context and field availability, and checks the
receiving API. It runs read-only without R or source downloads. This scoped check
does not replace the [full release gate](OFFLINE_RELEASES.md).

Game coverage is checked separately from numeric agreement: related weekly and
credit feeds can omit the same game. Historical captured inputs contain gaps for
`1999_01_BAL_STL`, `2000_03_SD_KC` and `2000_06_BUF_MIA`. Release reports describe
supplied versus completed games; agreement on available data is not a claim of
complete season totals.

## API and interface

`GET /api/players/{player_id}/receiving-splits` returns prepared overall rows,
breakdowns, aggregation components, field explanations and game/view coverage.
The service reads these in one transaction; malformed preparation returns 503.
It does not run the calculator or repair data.

The interface combines rates from supported components, displays missing values
with explanations and labels partial breakdowns as shown totals. Independent
whole-season totals retain production outside a view. See
[frontend data flow](FRONTEND_DATA.md) and [passing splits](PASSING_RELEASE_VALIDATION.md).
