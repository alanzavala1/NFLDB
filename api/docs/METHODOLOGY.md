# NFLDB Methodology

How this platform computes what it reports. Every section describes code that
actually runs; file references point at the implementation.

## How the power rankings are computed

Team power rankings are a net EPA-per-play model, not a media poll and not a
win-loss ranking. For each team and week, the builder accumulates offensive EPA
and defensive EPA allowed over every play up to that point in the season, then
scores a team as:

    off_epa_sum / (off_plays + 150) - def_epa_sum / (def_plays + 150)

Teams are ranked by that score within each season and week, highest first.

The `+ 150` in each denominator is deliberate early-season shrinkage. It acts as
150 plays of league-average (zero EPA) prior, so a team that has played one good
game is pulled toward the middle instead of topping the table on a small sample.
As real plays accumulate, the prior's weight fades and the score converges on
true net EPA per play.

Rankings are stored per week, so each row also carries the team's rank in the
previous week and the movement between them. See `api/power_rankings_builder.py`.

## How player game grades are computed

Per-game player grades come from raw play-by-play, not from box scores.

Raw scores are built by position group: quarterbacks, running backs, receivers
and tight ends are scored on total EPA across the plays they were involved in;
defenders on a weighted event score built from sacks, tackles for loss,
interceptions, pass breakups and similar events; kickers on made-versus-expected
by attempt distance.

Those raw scores are not comparable across position groups, so each is converted
to a percentile within its own position group across all seasons in the dataset,
then mapped through a fixed piecewise curve onto a 0-10 scale:

| Percentile | Grade |
|---|---|
| 5th | 4.5 |
| 25th | 5.7 |
| 50th | 6.5 |
| 75th | 7.3 |
| 90th | 8.0 |
| 98th | 9.0 |

So 6.5 is an average game, 8.0 is roughly a top-10% game, and 9.0 or better is
about the top 2% of games at that position. Because the curve is calibrated over
every season at once, adding a new season can shift historical grades slightly.
See `api/game_ratings_builder.py`.

## How the platform reconciles with official NFL stats

Official weekly player stats are the source of truth for counting stats. The
situational splits are computed independently from raw play-by-play, and are
required to reconcile back to those official totals exactly.

Getting there meant matching the NFL's own stat definitions rather than the
convenient play-by-play flags. Two examples that mattered: a pass attempt is a
completion, incompletion or interception, which is not the same as nflfastR's
`pass_attempt` column (that counts sacks in some seasons); and rushing attempts
include quarterback kneels.

This is enforced by tests, not by convention. `api/tests/test_reconciliation.py`
checks split counting stats and passing yards against official weekly totals for
exact equality, checks rushing and receiving yards within a tolerance that
accounts for lateral credit, and asserts that no impossible rates exist. The
deploy is gated on those tests passing inside the shipped image, so a release is
blocked when the data does not reconcile.

## What EPA means on this platform

EPA is standardized across every page so that one term means one number.
nflfastR's weekly `passing_epa` is the sum of `qb_epa` over dropbacks, and the
platform reproduces that definition exactly. "EPA per attempt" is therefore the
identical figure on the Splits, Leaders and Player pages.

This matters because EPA has several defensible definitions. Numbers here can
differ from another site's EPA without either being wrong; they will not differ
between two pages of this platform.

## How situational splits are built

Splits are stored in long format: one row per entity, season, category,
dimension and value, in the materialized `player_splits`, `defense_splits` and
`team_splits` tables. Because a split set partitions the same underlying plays,
a player's "overall" line always equals the sum of its splits, which is what
makes the reconciliation above possible.

Splits are single-dimension by design. You can ask for a passing line by
pressure, or by down, but not by pressure crossed with down, because storing
every cross-product would explode combinatorially and thin the samples past
usefulness. Play-level questions that genuinely need two conditions at once are
served by composing them from play-by-play instead.

Defensive splits are built by unioning per-defender credit columns into a single
events stream, and are counting stats only. There is no coverage or assignment
data in public play-by-play, so the platform does not report any.

## Why some data is missing for older seasons

Coverage limits are stated rather than papered over. When a question falls
outside them, the honest answer is that the data does not exist here.

- Play-by-play dataset: 1999 through 2025.
- Player, season, game-log and team stat tools: regular season only. Game
  schedules and results do include playoffs.
- Next Gen Stats tracking measures such as CPOE, time to throw and separation:
  2016 onward. The NFL's tracking data does not exist before that.
- FTN charting dimensions, meaning play action, blitz and defenders in the box:
  2022 onward, because that is when the charting source begins.
- Snap counts: roughly 2012 onward.
- Pass length and pass location: reliable from 2006 onward; sparse in 1999 and
  absent or extremely sparse from 2000 to 2005.
- Run location and gap, shotgun, EPA and success: 1999 onward, though run gap is
  naturally null on some run concepts.

## What the O-line grades do and do not measure

Offensive lines are graded as a unit, on what the line allows collectively: sack
and quarterback-hit rate, plus stuffed-run rate. Individual blockers are not
graded, because public play-by-play attributes nothing to a specific blocker on
a given play. The interface states this limitation rather than implying that
individual grades exist.

## How the question-answering agent is evaluated

The agent is measured on a gold set of plain-English questions whose expected
answers are computed live from the same verified query layer the agent calls, so
the evaluation cannot drift as the underlying data updates. Each question is
graded twice: on routing, meaning whether the model called the expected tool with
the expected arguments, and on the answer, meaning whether the figure or name it
reported matches ground truth.

The evaluation is opt-in because it makes billed model calls. It has caught at
least one real regression: a broken tool chain scored 88% during development, and
the eval isolated the cause.

To test whether the typed-tool design is necessary at all, the repository also
contains a text-to-SQL baseline: the same model, given the full database schema
and asked to write SQL directly, graded on the identical questions with the
identical graders. The baseline was measured twice, once on the raw schema and
again after adding a full data dictionary, to remove missing documentation as an
explanation for the gap.

## Why the agent uses typed tools instead of writing SQL

The agent answers by calling typed tools that wrap the platform's already
reconciled query layer. It never sees the database schema and never writes SQL.

This is the design decision that defines the feature. Text-to-SQL would let the
model re-derive stat definitions on the fly, and the reconciliation work
described above is precisely the set of definitions it would get wrong: counting
sacks as pass attempts, dropping quarterback kneels from carries, summing the
wrong EPA column. Typed tools make that class of error impossible, because the
model can only ask questions that have already been verified as correct.

The model still chooses which tools to call and how to phrase the answer. What
it cannot do is redefine what a statistic means.
