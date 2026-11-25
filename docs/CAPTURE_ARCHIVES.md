# Capture archives

A capture archive transports core/receiving inputs and passing exports between
workers. It preserves original manifests and their declared files without
rewriting source identities. Python ZIP64 support handles large archives.

Run from `api/`, using new output paths with existing parent directories:

```sh
uv run --locked python -m jobs.captures pack \
  --core-inputs data/core-inputs --passing-inputs data/passing-inputs \
  --output data/captures.zip

uv run --locked python -m jobs.captures restore \
  --archive data/captures.zip --output data/restored-captures
```

The examples use Bash continuations. Restore prints the `core` and `passing`
paths to use in preparation or validation. Keep them with their root
`capture-map.json`: it resolves original machine paths, including Windows paths
on Linux, without changing hashed manifests. Unmapped references fail.

Packing follows collection indexes and includes each source run's declared,
hash-bound files. Unlisted logs and diagnostics are omitted. Restoration checks
the exact inventory, sizes, hashes and safe relative paths. Duplicate, undeclared,
symlink and escaping entries are rejected. A failed restore removes only files
it created; it never overwrites an existing destination.

Archive integrity does not replace statistical validation or authenticate its
publisher. Use the controlled artifact store and retain the original receipts.
Packing does not fetch new data, run R, advance watermarks or publish a release.
See [source provenance](UPSTREAM_PROVENANCE.md), [local releases](OFFLINE_RELEASES.md)
and [cloud publication](CLOUD_RELEASES.md).
