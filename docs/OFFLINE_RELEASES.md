# Local data releases

A release bundles a validated database, source watermarks and their manifests.
Building or selecting a local release does not upload data or deploy the website.
For the complete automated flow, use [refresh automation](NATIVE_REFRESH_AUTOMATION.md).

Run commands from `api/`. Examples use Bash line continuations. The source database
must be closed with no pending WAL; output paths must be new and their parents
must exist. Core and passing collections must cover every stored season required
by validation.

## Prepare and bundle

```sh
uv run --locked python -m jobs.refresh prepare watermarks.json \
  --source data/source.duckdb --candidate data/candidate.duckdb \
  --release data/new-release --seasons 2026 \
  --core-inputs data/core-inputs --passing-inputs data/passing-inputs
```

Preparation copies the source into a separate writable candidate, refreshes the
requested sources and rebuilds analytics against the supplied collections.
Historical calculator exports are reused. The combined flow checks the candidate
and runs full source/statistical/API validation during release packaging.
The ordinary standalone candidate command performs full validation by default.

To bundle an already prepared database:

```sh
uv run --locked python -m jobs.release build \
  --database data/candidate.duckdb --output data/new-release \
  --core-inputs data/core-inputs --passing-inputs data/passing-inputs \
  --watermarks watermarks.json
```

The bundle contains `nfl.duckdb`, `validation.json`, `watermarks.json` and
`release.json`. The completion manifest is written last and binds file sizes,
hashes and validation-policy identity. Omitting `--watermarks` creates an empty
acknowledgment map; packaging alone does not establish source freshness.

## Verify and select

```sh
uv run --locked python -m jobs.release verify --release data/new-release
uv run --locked python -m jobs.release select-local \
  --release data/new-release --pointer data/current.json
```

Initial selection requires an absent pointer. To update it, pass
`--expected-pointer-sha256` with the hash previously read. An exclusive writer
reservation and atomic replacement prevent stale updates. Keep the pointer
outside release directories. After a crash, confirm the publisher has stopped
before removing a stale lock file.

Database and watermarks are selected together. The operation does not replace
an open serving file or change `NFL_DB_PATH`.

## Source acknowledgments

A watermark records a consumed upstream version. Refresh observes versions before
and after preparation and advances only stable, successfully loaded inputs or
supported empty optional feeds. Failed, missing or changed sources retain their
old marks. RDS keys require matching [native source proof](UPSTREAM_PROVENANCE.md).

Release verification checks file integrity and compatibility with the current
validation policy. Statistical validation describes captured inputs, not future
upstream changes. See [cloud publication](CLOUD_RELEASES.md) to upload and select
an immutable cloud release.
