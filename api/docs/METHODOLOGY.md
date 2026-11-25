# NFLDB methodology

How NFLDB calculates statistics and ratings, with source coverage limits.

## How the power rankings are computed

Rankings compare offensive EPA per play with EPA allowed by the defense:

```text
score = off_epa_sum / (off_plays + 150) - def_epa_sum / (def_plays + 150)
```

EPA estimates a play's effect on expected points. The extra 150 plays pull small
early-season samples toward zero; their effect shrinks as teams play more snaps.
Scores, ranks and accompanying win-loss records stop at the selected week.

Source: `api/power_rankings_builder.py`, `api/services/power_rankings.py`.

## How player game grades are computed

Raw scores depend on position:

| Position | Basis |
|---|---|
| QB | Accumulated quarterback EPA |
| RB, WR, TE | EPA on attributed plays, with a lost-fumble penalty |
| Defense | Weighted recorded events |
| Kicker | Field goals relative to expected success by distance, plus extra points |

Eligible games are ranked within each position group across loaded seasons,
then mapped to a 3–10 scale. A 6.5 is the median, 8.0 the 90th percentile and
9.0 the 98th percentile (roughly top 2%). Missing data or insufficient activity
can leave a player unrated. These are statistical ratings, not film grades;
new data can change historical ratings through recalibration.

Source: `api/game_ratings_builder.py`.

## How the platform reconciles with official NFL stats

Offline validation compares supported counts and yards with captured nflfastR
outputs and weekly totals. Detailed player credits retain lateral and multi-passer
production. Checks cover stored seasons, source/game coverage and API responses
before publication. Missing upstream games or fields remain explicit gaps.

Source: `api/pipeline/receiving_validation.py`, `passing_validation.py`,
`reconciliation.py`; deployment tests: `api/tests/test_reconciliation.py`.

## What EPA means on this platform

EPA measures the change in expected points on a play. Positive EPA favors the
offense. Rates depend on attribution and the population counted:

- Prepared passing EPA includes supported quarterback EPA from sacks, divided
  by official pass attempts.
- Passing success percentage counts positive-EPA attempts. Completion percentage
  over expected (CPOE) uses the subset with a completion-probability estimate.
- Receiving EPA uses the original target role and requires a matching verified
  population.

Combined split rates divide summed numerators by matching denominators rather
than averaging displayed percentages. Other pages or sites can use different
populations; compare definitions first. Null means unavailable, not zero.

Source: `api/pipeline/passing_metrics.py`, `receiving_target_metrics.py`.

## How situational splits are built

Splits group statistics by one situation, such as down or opponent. The page
compares one dimension at a time instead of every cross-product of conditions,
which would create very small samples.

Passing and receiving use the pinned nflfastR calculator on filtered plays.
Prepared records retain coverage and rate components. Unknown context can leave
production outside a breakdown while retaining it in whole-season totals.
Rushing, defensive and team splits have separate builders. Defensive events do
not reveal coverage assignments.

See [receiving](../../docs/RECEIVING_RELEASE_VALIDATION.md) and
[passing](../../docs/PASSING_RELEASE_VALIDATION.md) for calculation and validation details.

## Why some data is missing for older seasons

Published play-by-play analytics begin in 1999. Available games depend on the
release; the current season is partial. Schedules include playoffs, while many
summaries and prepared splits use regular-season games.

| Data | Known boundary |
|---|---|
| Receiving targets and dependent rates | Unavailable in 2003–2008 |
| Receiving yards after catch | Unavailable before 2006 |
| Receiving air yards | Unavailable before 2009 |
| NGS tracking summaries | Source starts in 2016 |
| FTN play action, blitz and box counts | Source starts in 2022 |
| Snap counts | Source starts in 2012 |

Supported receptions, yards and touchdowns remain visible. Later seasons can
still have gaps; prepared responses explain affected fields and games. NGS
tracking summaries and play-derived modeled statistics are separate sources.

Source: `api/services/receiving_coverage.py`, `api/pipeline/vendor_sources.py`.

## What the O-line grades do and do not measure

Offensive lines are graded as a unit using sacks, quarterback hits and stuffed
runs relative to opportunities. Eligible team-game scores use the historical
percentile scale.

Individual blockers are not graded: public play-by-play does not identify each
blocker's responsibility. Quarterbacks, runners and opponents also affect these
outcomes, so the grade measures unit results rather than isolated blocking skill.

Source: `api/ol_grades_builder.py`.

## How the question-answering agent is evaluated

An opt-in evaluation checks tool routing/arguments and answer accuracy against
expected query results. Model evaluations make billed API calls and are separate
from ordinary unit tests. A run measures those questions on its data/model versions.

Source: `api/tests/test_ask_eval.py`, `api/tests/test_ask_eval_graders.py`.

## Why the agent uses typed tools instead of writing SQL

The assistant calls predefined tools with validated arguments. They use shared
services or SQL constructed from approved filters, keeping supported statistical
definitions in code. This limits the questions the tools can express. The model
can still choose the wrong tool or misread a result.
