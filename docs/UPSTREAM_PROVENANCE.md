# Source provenance

The native calculator consumes three RDS assets for each season:

| Refresh key | Repository / release | Asset |
|---|---|---|
| `pbp_rds` | `nflverse-data` / `pbp` | `play_by_play_YEAR.rds` |
| `weekly_rds` | `nflverse-data` / `stats_player` | `stats_player_week_YEAR.rds` |
| `playstats` | `nflverse-pbp` / `playstats` | `play_stats_YEAR.rds` |

Detailed player credits come from the third feed. Tracking only the Python
parquet feeds would not identify all inputs used by `calculate_stats`.

## Capture and verification

From `api/`, with the [locked R environment](../api/r/README.md) and a new output path:

```sh
uv run --locked python -m jobs.capture_core --season 2026 \
  --output data/captured-2026 --rscript PATH_TO_RSCRIPT \
  --r-library PATH_TO_LOCKED_LIBRARY
```

The command records GitHub asset identities and published digests, downloads the
raw bytes and verifies their hashes. A pinned R comparison checks the consumed
inputs against those assets by typed columns, row order and row counts; serialized
RDS hashes alone cannot establish equality. Metadata observations before/after
must agree. Missing assets, missing digests or changed inputs fail capture.

`upstream-proof.json`, comparison artifacts and source files are bound into the
receiving manifest. Conversion creates the core bundle; `capture.json` is written
only after successful completion. This operation opens no database and advances
no watermarks.

## Watermarks and replay

```sh
uv run --locked python -m jobs.refresh native-check watermarks.json
```

This reads upstream versions without modifying watermarks. Refresh acknowledges
a version only when it remained stable, the proof matches it and the corresponding
source was loaded. Older captures without proof can support statistical replay
but cannot acknowledge the new RDS keys. RDS evidence does not acknowledge parquet keys.

[Capture archives](CAPTURE_ARCHIVES.md) preserve the proof files. Source identity
does not establish complete game coverage or correct every upstream statistic;
the [release validation](OFFLINE_RELEASES.md) remains required.
