# Receiving integration: complete snapshot checks

The ordinary validator can now inspect the official receiving integration with
its captured source inputs. This is a diagnostic checkpoint: the actual complete
history still fails a passing check, and the official publication guard remains.
No serving database, raw statistics, deployment setting or frontend changed.

## One validation entry point

From `api/`, using the closed coordinated development database:

```powershell
uv run --locked python -m jobs.validate `
  --database data/coordinated-analytics-refresh-20261026.duckdb `
  --core-inputs data/receiving-refreshed-history-collection-20261026
```

The process opens DuckDB read-only. It cannot repair tables, download sources,
execute R or stamp a validation result into the database. `jobs.prepare` forwards
its captured-input path to this same subprocess. A failed outer preparation
still removes only its new candidate and preserves its source.

Without captured inputs, official receiving records are rejected immediately.
Passing a captured path for a legacy-only snapshot is also rejected. Any of the
three official receiving metadata tables activates this boundary, so deleting
only the preparation marker cannot bypass it. Preview tables remain rejected.

## Checks composed for official inputs

The full diagnostic runs:

1. Existing builder schemas, unique/non-null keys and lookup-index checks.
2. Recorded core-source outcomes and exact stored counts, using the same
   preparation-record checker as the candidate wrapper.
3. Source-bound receiving replay for every loaded REG season: exact captured
   core rows, qualification, all 17 views, independent whole/excluded references,
   metadata hashes and NULL policies. Player-game catches, yards and TDs remain
   exact checks, including players below split admission.
4. Stored FTN agreement with the shared projection in every bound capture.
5. Existing passing/rushing and defender admission, seasonal coverage, awards,
   finite/bounded ratings and split-rate checks.
6. Game coverage in player-game stats, ratings and O-line grades for **every
   supplied REG game**. One remaining row in a season cannot disguise a partial
   rebuild. This does not invent rows for games absent from the source.
7. Passing/rushing/defensive reconciliation for every loaded season. All
   statistical failures are listed together after this loop. Existing yardage
   allowances are unchanged; passing attempts/yards still allow zero mismatches.

For official receiving, replay replaces the old Down-based receiving admission
and split-total checks. A partial Down view is not a whole-season reference.
Legacy-only validation retains its existing receiving checks.

The release guard remains after these checks. Even an otherwise clean official
fixture cannot return publication success. HTTP validation follows successful
snapshot validation; this real blocked run therefore does not reach that phase.
The previous coordinated proof's 73 HTTP checks remain separate evidence.

## Executed result, October 26, 2026

The real command reached all 28 seasons, 1999–2026. Receiving replay matched
**266,762 rows and all whole/coverage records**. All 84 player-game receiving-count
checks were zero, source/preparation/FTN checks passed, and all supplied games
had downstream coverage. The reconciliation loop completed every year.

The command exited **1**, correctly rejecting the database for two checks tied
to one passing attribution case:

| 2004 Vinny Testaverde season totals | Weekly source | Passing Down splits |
|---|---:|---:|
| Attempts | 495 | 494 |
| Passing yards | 3,532 | 3,518 |

The differing week is 14. Play `2004_14_NO_DAL / 4462` describes Testaverde's
completion to Richie Anderson, a lateral to Keyshawn Johnson, and Johnson's
intercepted throw. Its single passer ID names Johnson while its passing-yard
field is 14. The weekly source gives Johnson one attempt, zero completions,
zero passing yards and one interception. The current custom passing split path
cannot assign both quarterbacks' credits from that single passer field.
No player-specific correction or larger mismatch allowance was added.

Two initial EPA failures were validation reconstruction errors, now fixed:
Roethlisberger in 2005 and Yates in 2011 had a fourth-down bucket containing
only a sack. EPA per attempt is correctly NULL with zero attempts. Multiplying
that rate by zero lost the bucket's negative EPA. The checker now recovers that
numerator from the same season's REG source plays, with the existing passing
EPA play-type filter. It still rejects missing buckets, invented zero rates,
unknown positive-attempt rates and wrong numeric rates. No stored EPA changed,
and the existing 0.005 rate tolerance is unchanged.

Ignored evidence:

- `api/data/receiving-full-release-checks-20261026.log`
- `api/data/receiving-full-release-proof-20261026.json`
- `api/data/release-2004-passing-attribution-20261026.json`
- `api/data/receiving-release-controls-20261026.{xml,log}`

The final complete backend suite passed **1,222 tests, two skipped** (354.09s),
including all 19 new release-check controls. The focused controls passed in
18.51s. Full results are `api/data/receiving-release-backend-20261026.{xml,log}`.
The serving, earlier API proof and coordinated development files kept their
previous SHA256 values after all jobs closed; none had a pending WAL. Passing
software tests does not override the real-data failure recorded above.

## Remaining release work

The passing-credit investigation below verifies a repeatable upstream counting
solution for the 2004 case. It still needs an isolated passing adapter preview,
qualification/efficiency-metric checks and all-history validation before build
integration. The recorded
receiving counts and usable passing data should remain available while the
affected attribution is addressed. Separately audit metric availability in the
legacy profiles/leaders/game endpoints; their existing masks cover historical
targets, while the dedicated receiving API has the broader YAC/air/NULL policy.
Only after the complete real-data checks, legacy-consumer audit and release
review pass should the official publication guard be removed. Refresh/deployment
migration and retirement of request-time writes remain later pipeline work.

## Passing attribution investigation, October 26

The missing credit is present in the already captured detailed play statistics:

| Player | Detailed stat ID | Credit on play 4462 |
|---|---:|---|
| Vinny Testaverde | 15 | Completion, 14 passing yards |
| Keyshawn Johnson | 19 | Intercepted pass, zero passing yards |

The existing receiving producer saves all detailed credits, not only receiving
credits. These two passing records are already in its bound `credits-2004.csv`
and RDS capture. The single-row PBP representation loses this distinction for
our custom passing aggregation, while the maintained calculator uses the
separate records. Its [passing counting implementation](https://github.com/nflverse/nflfastR/blob/4fc75e88b308ed592e11700e580e9e5380bdc46b/R/calculate_stats.R)
sums completion/attempt/yardage/interception stat IDs rather than assigning all
of a play's passing counts to `passer_player_id`.

An actual **unmodified** `nflfastR::calculate_stats` run passed in the pinned
R 4.6.1 / nflfastR 6.0.0 / nflreadr 1.5.1 environment. It read the frozen full
2004 PBP/weekly inputs and downloaded detailed credits through its normal
loader. The fresh five-column credit projection matched the previous capture,
preserving duplicate records. No namespace, calculator or transport was patched.

The one-play result assigns Testaverde one attempt, one completion and 14 yards;
Johnson receives one attempt, no completion, no passing yards and one
interception. The whole season and four Down calculations also passed:

- All six passing count fields matched weekly reference totals for every
  identified player, including low-volume players. There were 117 players with
  nonzero passing counts or sacks suffered.
- Whole versus weekly, summed Down versus weekly, and summed Down versus whole
  had zero mismatches in attempts, completions, yards, TDs, interceptions and
  sacks suffered: all 18 metric comparisons passed.
- Testaverde's calculated whole/Down season totals are 495 attempts, 297
  completions and 3,532 yards, matching the already correct stored player-game
  totals. The current custom Down rows remain 494 / 296 / 3,518.

A separate read-only scan of all 28 captured seasons, 1999–2026, found exactly
one supplied REG nonconversion play with more than one identified player holding
passing stat IDs 14/15/16/19: this same play. Every scanned credit CSV matched
its captured hash first. This census covers that specific multi-passer pattern;
it does not certify all other passing counts or source classifications.

The investigation therefore supports extending the existing offline calculator
integration to passing counts. A one-player override is unnecessary. EPA, CPOE,
success rates, air yards and qualification are separate integration questions;
this count proof does not certify them or retire the release guard.

Ignored evidence: `api/data/passing-attribution-probe-20261026/proof.json`, its
exact-play/whole/Down CSVs, `passing-attribution-probe-20261026.log`, the runner
`investigate_passing_2004_20261026.R`, and
`passing-multiple-passer-audit-20261026.json`. No database was changed.
