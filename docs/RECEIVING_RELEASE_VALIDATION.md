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

Investigate a repeatable passing-credit solution for the 2004 case. The recorded
receiving counts and usable passing data should remain available while the
affected attribution is addressed. Separately audit metric availability in the
legacy profiles/leaders/game endpoints; their existing masks cover historical
targets, while the dedicated receiving API has the broader YAC/air/NULL policy.
Only after the complete real-data checks, legacy-consumer audit and release
review pass should the official publication guard be removed. Refresh/deployment
migration and retirement of request-time writes remain later pipeline work.
