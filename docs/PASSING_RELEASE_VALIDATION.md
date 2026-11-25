# Passing splits

Passing splits use source-bound nflfastR exports alongside the captured receiving
inputs. Whole-season totals and situational rows are prepared offline; the API
reads them without running R or downloading data.

## Counts and metrics

Detailed player credits supply passing attempts, completions, yards, touchdowns,
interceptions and first downs. The adapter checks source/weekly agreement before
applying the existing 50-dropback season admission rule. Situation membership
comes from the same recorded plays used by receiving.

Modeled metrics need matching play-level attribution:

| Component | Meaning |
|---|---|
| `epa_sum` | Verified quarterback EPA, including sacks |
| `successes` | Attempts with positive EPA |
| `cpoe_sum`, `cpoe_count` | Sum/count of modeled completion observations |

EPA per attempt divides `epa_sum` by official attempts. Success percentage uses
attempts; CPOE uses modeled observations, not all attempts. A sack-only bucket can
retain an EPA numerator while its own per-attempt rate is undefined. Counts remain
visible when an attribution mismatch makes a modeled metric unavailable.

Air yards and YAC require matching coverage and are unavailable before 2006.
Passing YAC follows credited yards minus completed-pass air yards. First downs
are independently credited counts. Multiple throws on one play share the source
play's depth/direction labels; they do not have separately reconstructed context.

## Export and validate

From `api/`, with matching core inputs and the [locked R environment](../api/r/README.md):

```sh
uv run --locked python -m jobs.passing_preview \
  --core-inputs data/core-inputs --exports data/passing-2026 --season 2026 \
  --rscript PATH_TO_RSCRIPT --r-library PATH_TO_LOCKED_LIBRARY
```

The exporter defaults to all 17 views. A `--dimensions` subset is diagnostic and
cannot enter a complete build. Output paths must be new. Exports bind their
season's source/calculator identity, so unchanged historical exports can be reused
when another season changes or captures move between workers.

`jobs.passing_inputs` indexes exports into a collection; `jobs.refresh_inputs`
combines refreshed seasons with a historical core/passing pair. Collections must
cover every stored season required by the build. The
[refresh worker](NATIVE_REFRESH_AUTOMATION.md) performs this composition automatically.

Validate the prepared database with both matching collections:

```sh
uv run --locked python -m jobs.validate \
  --database data/candidate.duckdb --core-inputs data/core-inputs \
  --passing-inputs data/passing-inputs
```

Validation replays rows, metadata, metric components and API responses. Passing,
receiving and rushing replacements share a season transaction; a late failure
rolls them back together. Official records cannot fall back to an input-free
legacy build. See [local releases](OFFLINE_RELEASES.md).

## API and interface

`GET /api/players/{player_id}/passing-splits` returns season status, independent
overall rows, classified rows, field explanations, aggregation components and
omitted-production/game coverage. Missing summary preparation is unverified;
malformed records return 503 rather than being rebuilt.

The page adds full-precision components before dividing. An empty CPOE population
has zero observations; a missing component remains unknown. Whole-season totals
do not depend on whether a play has a down or other situational label.
Partial breakdowns show their own totals and exclusions. See
[frontend data flow](FRONTEND_DATA.md) and [methodology](../api/docs/METHODOLOGY.md).
