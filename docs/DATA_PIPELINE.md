# Data preparation

A separate worker builds the database served by the website. Preparation runs
before publication; it does not run during visitor requests.

```text
Captured inputs → source loading → player/game statistics → analytics
                → validation → release bundle → publication → deployment
```

## Inputs and storage

Core inputs are play-by-play, weekly player statistics, schedules and rosters.
Passing and receiving also use detailed player credits through the pinned
nflfastR calculator. Captures bind source bytes, calculator code and runtime
versions so validation can replay the calculation.

`pipeline/loading.py` coordinates source adapters and storage. The shared optional
asset catalog in `pipeline/vendor_sources.py` supplies both download locations and
refresh tracking. Normalization and season/table replacement are separate steps.

| Optional-source outcome | Treatment |
|---|---|
| `loaded` | Store validated rows and acknowledge the consumed version |
| `empty` | Retain existing rows; acknowledge a successfully examined empty version |
| `not_found` or known network failure | Retain rows and the old watermark |
| `unsupported` | Skip years outside source coverage |
| `unsupported_format` | Retain data when the source lacks the required format |

Invalid schemas, parsing errors and unexpected storage/programming failures stop
preparation. They are not treated as ordinary source outages. See the
[data map](DATA_MAP.md) for source families and relationships.

## Calculations

`pipeline/player_stats.py` builds player-game statistics from official weekly
records and play-derived categories. `pipeline/analytics.py` orders the derived
builds after their inputs exist:

- Team season analytics and weekly power rankings.
- Player game ratings and offensive-line unit grades, calibrated across history.
- Offensive player, defensive and team situational splits.
- Career summaries, similar-player rankings and lookup indexes.

Passing and receiving replay official captured exports. Other categories retain
their own builders and validation rules. Counts, modeled metrics and context
coverage are separate: a known count does not establish that EPA or a particular
situational label is available. See [receiving](RECEIVING_RELEASE_VALIDATION.md),
[passing](PASSING_RELEASE_VALIDATION.md) and [methodology](../api/docs/METHODOLOGY.md).

## Candidate and release

A candidate is a new writable copy of a closed source database. The worker
prepares it in a separate process, then closes it for read-only validation.
Existing source files are never overwritten. A pending DuckDB WAL must be
checkpointed by closing its writer before copying.

Validation checks schemas/keys, captured inputs, official calculations,
statistical reconciliation, supplied-game coverage and representative API reads.
It reports upstream gaps rather than fabricating missing games or fields.
Release packaging validates the candidate and copies the verified bytes into a
new immutable bundle.

Use [scheduled refresh](NATIVE_REFRESH_AUTOMATION.md) for the complete automated
flow, or [local release commands](OFFLINE_RELEASES.md) for manual preparation.
[R setup](../api/r/README.md), [capture archives](CAPTURE_ARCHIVES.md) and
[source provenance](UPSTREAM_PROVENANCE.md) describe the input boundary.
