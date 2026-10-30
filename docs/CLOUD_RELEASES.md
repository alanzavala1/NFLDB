# Versioned cloud release uploads

The offline worker first creates and validates a native bundle. Publication then
uploads that bundle and its matching capture ZIP into one new GCS prefix. The
publisher never selects a current release or deploys the website.

```text
gs://BUCKET/native/releases/RELEASE_ID/
  reservation.json     exclusive upload reservation
  nfl.duckdb           validated database
  validation.json      native source/statistical/API validation report
  watermarks.json      acknowledged source versions
  release.json         native bundle hashes and validation policy
  captures.zip         matching portable core/passing inputs
  publication.json     completion manifest, uploaded last
```

`release.json` is the existing local bundle manifest. `publication.json`
connects that bundle to its captured inputs and records each uploaded file's
size, SHA256, MD5 and GCS generation. A generation identifies a particular cloud
object version; readers use it rather than silently accepting newer bytes at
the same name. The upload receipt also records the completion manifest's own
generation and SHA256.

## Upload

Use the existing authenticated Google Cloud CLI. From `api/`, with the locked
Python environment and an unused destination:

```powershell
uv run --locked python -m jobs.publish upload `
  --release data/releases/validated-release `
  --captures data/matching-captures.zip `
  --destination gs://BUCKET/native/releases/UNIQUE_RELEASE_ID
```

Linux accepts the same options with ordinary shell line continuations. The
worker's existing Workload Identity authentication can supply CLI credentials;
no additional Python cloud SDK or service-account key is introduced. On Windows,
the adapter invokes the installed SDK's bundled Python directly, keeping local
paths out of `cmd.exe` expansion.

The publisher:

1. Holds a read-only database lock, fingerprints the source bytes, and verifies
   the native bundle using the existing validation-policy and file-hash checks.
2. Streams every ZIP member, checks its SHA256 and validates the complete graph
   of manifests, declared files and child references. It recomputes the root
   collection identities and compares them and the seasons to the database's
   validation report. It then confirms that the source bytes stayed unchanged
   throughout those content checks. This needs no second extracted copy or R calculation.
3. Creates an exclusive reservation, then uploads each of the five payloads
   using `--if-generation-match=0`. Existing objects cause failure.
4. Supplies each expected MD5 for server-side transfer validation, then checks
   remote size/checksum metadata and records the returned generation.
5. Rechecks local inputs, the native bundle and the publisher code before
   uploading the completion manifest last.
6. Reads the pinned completion manifest back and verifies every recorded object
   generation and the native metadata links.

The native `validation_code_sha256` still identifies the analytics/API policy
that validated the database. A separate `publisher_code_sha256` records the
transport implementation. Transport changes can retain a compatible publication
format without changing the statistical validation record.

These are standard Cloud Storage operations. Google documents the
[create-only generation precondition](https://docs.cloud.google.com/storage/docs/request-preconditions)
and [server validation with `--content-md5`](https://docs.cloud.google.com/sdk/gcloud/reference/storage/cp).
SHA256 identifies payload bytes in the publication and is checked again when
files are downloaded; GCS's MD5 check protects the upload transfer.

## Verify an uploaded release

Record the JSON receipt emitted after upload. To check its exact manifest:

```powershell
uv run --locked python -m jobs.publish verify `
  --destination gs://BUCKET/native/releases/UNIQUE_RELEASE_ID `
  --manifest-generation GENERATION_FROM_RECEIPT `
  --manifest-sha256 SHA256_FROM_RECEIPT
```

Verification reads the recorded generations, compares remote transfer checksums
and sizes, checks SHA256 for the small downloaded metadata files, and checks the
native report, watermarks, bundle hashes, source identities and policy. It does
not download the large database/ZIP or rerun statistical validation. Deployment
must download the pinned objects, check their SHA256 values and run the existing
native bundle verifier before baking the database into an image.

Omitting the optional manifest identity discovers the prefix's current
completion marker, then pins its generation for the verification. Automated
deployment should consume the recorded identity from selection.

## Failure handling

An incomplete prefix has no completion manifest and cannot be treated as a
published release. Failed uploads retain their reservation and any uploaded
objects for diagnosis; retries use a new release ID. The uploader never deletes
existing cloud objects or overwrites previous release files.

A client can lose its connection after the server has accepted the final
manifest. In that case, verify the existing destination before deciding whether
a new upload is needed. A valid completion manifest still represents a complete
upload even if the original caller did not receive its acknowledgment.

Immutability is enforced by the publisher's create-only protocol. Bucket
retention/IAM settings remain a separate concern. If an externally replaced
object's recorded generation is unavailable, verification fails; it does not
fall back to another version.

## Verified result: October 30, 2026

151 distinct targeted checks passed on Windows and Ubuntu 24.04. They cover
partial uploads, conflicting/concurrent publishers, changed local files and
publisher code, archive replacement during preflight, corrupt/mismatched capture
graphs, remote corruption and generation-pinned reads. Existing release,
candidate, source-provenance and refresh controls are included in that count.

A real probe using Google Cloud SDK 572.0.0 rejected an incorrect MD5 and a
second create-only write, and successfully read the pinned object version. A
subsequent real upload interrupted by an authentication-service DNS failure
left only a reservation and no completion manifest.

The completed upload contains the previously validated 1999–2026 database and
its matching 4,741-file capture archive, plus the three small native metadata
files. The ordinary upload command completed, and a separate ordinary verify
command matched its exact manifest generation/SHA256 and returned the same
receipt. The local bundle/archive and all five protected original databases
remained intact. The legacy cloud database/watermarks were unchanged during the
final upload. No native release was selected or deployed by this work.

The local end-to-end upload, including preflight and integrated verification,
took 17 minutes 14 seconds; the two large payloads total approximately 2.13 GB.
This reflects the local network connection, not a hosted-worker benchmark. The
large objects were checked with server-validated MD5 and pinned generation/size
metadata; download-time SHA256 verification remains part of the next consumer
integration. Publishing existing captures acknowledges no new upstream versions.

The receipt, standalone verification, independent cloud proof, test XML, SDK
version and diagnostic logs are kept under ignored `api/data/` with the
`publication-*-20261030` prefix. Keep the saved receipt for the next selection
step; it identifies the exact completed cloud release.

## Remaining integration

The legacy `refresh.yml` and `deploy.yml` still use the bucket's original
`nfl.duckdb` and standalone watermarks. Uploading a new native release leaves
that serving path intact. The next work is a generation-matched selection
pointer, downloads of its pinned release, deployment/rollback handling, and the
workflow that captures and prepares refreshed native inputs. Ask model/streaming
changes and alternative frontend hosting remain separate milestones.
