# Rust increment 31: payload operation diagnostics without retry-policy changes

Increment on `feature/rust-transfer-coordinator`, 2026-10-15. Improves the generic
payload failures measured in [increment 30](RUST-INCREMENT-30.md). Retry timing,
three-failure review, durable phases and audited resume/replay are unchanged.
No dependency, deployed executable, public API/status field, schema 10, binding
version 3 or persisted receipt format changes. Production NFS/deletion stay off.

## Diagnostics and unchanged effects

Private `mover-fs::payload_io` labels the existing operations, preserves a numeric
OS errno when available and emits fixed safe operator guidance. Production still
issues the same native reads, write-all and sync calls in the same order. The
wrapper adds no retry, allocation, transition or payload pass; integrity stays 3N.

| Operation label | Existing call |
|---|---|
| `payload_source_read` | Source read during copying |
| `payload_copy_write` | Destination staging write-all |
| `payload_copy_file_sync` | Completed staging file sync |
| `payload_copy_directory_sync` | Staging namespace sync after copying |
| `payload_verification_read` | Destination verification/recovery/custody reread |
| `payload_publication_file_sync` | Published payload file sync |
| `payload_publication_staging_sync` | Old staging namespace sync after publication |
| `payload_publication_directory_sync` | Final parent namespace sync after publication |

Example real destination-full log detail:

```text
payload_copy_write errno=28; storage full; restore approved capacity; preserve source/state; resume only if review required
```

EIO gets fixed storage-inspection guidance. Errors without numeric errno expose
only fixed `interrupted`, `write_zero` or `other` labels; original error text is
never formatted. Display/Debug and the existing bounded private diagnostic path
do not echo payload bytes, paths or arbitrary error strings. Unrelated namespace,
binding and manifest errors retain their existing diagnostics; this is not a
complete error-classification or persisted operator-error API.
Logical digest/identity refusals also retain their existing fallback; this
increment labels native payload I/O rather than redefining those decisions.

Diagnostic text remains separate from effect receipts. Existing worker errors
clear transfer/manifest authorization and follow the same parent failure path.
In particular, a publication sync error can follow a successful link/rename;
the valid final file may exist while PublishIntent/review remains durable. The
diagnostic never grants commitment, deletion, collision overwrite or takeover.

## Qualification and tests

Retained qualification-only `FILE_MOVER_QUALIFICATION_PAYLOAD_FAULT` selects one
of the eight labels above. It returns ENOSPC before copy-write, or EIO before
the other selected native call. Production never reads this variable. These
simulated return values are not hardware EIO, power-loss or in-flight RPC proof.

The local API test loops through all eight boundaries: require 202, source/path
reuse retention, no completion manifest, exactly three failures and the original
phase (Intent, Copied or PublishIntent). It checks precise safe logs and preserves
an already published file when publication sync fails. Restart without the fault
must leave review intact; explicit audited resume/replay must recover normal
commitment. Production must ignore every selector and complete normally.
The diagnostic unit test covers operation/errno, fixed actions, bounded ASCII,
unknown/custom error text, Interrupted/WriteZero and sanitized Debug output.

The actual bounded NFS destination-full fixture now requires exactly three
`payload_copy_write errno=28` details with capacity/preservation guidance in each
live/restart case. It retains all prior custody, partials, health/status,
three-failure review, resume/replay and commitment checks. No error is injected
in those real-capacity cases. Full ownership/runtime regression remains required
after the filesystem-path change, alongside enrollment/delivery storage cases.

## Validation

Production gate `20261016T012557Z-12a0b124` PASSED 154 tests per debug/release
profile. Qualification gate `20261016T012557Z-361d9522-nfs-qualification` PASSED
155 per profile. Both passed formatting/Clippy, all 20 executable ELF audits per
mode, six negative controls and exact pinned SLES target execution. Each profile
passed all 64 API tests, including the eight selected payload failure boundaries.
Both archive hashes and complete 54-file inventories/content match the current
Rust tree. The external graph remains 42 packages and highest required GLIBC
remains 2.18. See [production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

Full NFS run `nfs-20261016T013801Z-a01edfff` PASSED with exit status 0 and
`cleanup_errors: []`: six directional baselines, 24 ownership/enrollment cases,
22 runtime interruption cases, four enrollment storage cases and four delivery
storage cases. All four three-minute outages retained one worker with responsive
health/status and recovered successfully. OS inherited-lock, interrupted metadata,
isolated bootstrap shutdown and production refusal controls also passed. See
[full diagnostic/NFS evidence](RUST-NFS-PAYLOAD-DIAGNOSTICS-EVIDENCE.json).

All four real destination-full live/restart cases emitted exactly three
`payload_copy_write errno=28` details with the fixed capacity/preservation action,
without the old generic diagnostic or source/destination paths. Each retained the
original source and 1 MiB partial prefix, reached review after exactly three failed
attempts, stayed in review after capacity restoration, then committed the same job
on attempt 4 only after audited resume/replay. Restart preserved both review and
committed evidence. Old partials and the recorder's reused path stayed intact.
The maximum sampled health/status pair was 6.36 seconds including host engine/
transport overhead, below the selected 15-second fixture window; this is not a
production latency SLO. Native ENOSPC is distinct from the synthetic EIO tests.

Verified recorded driver hashes and gate source/artifact provenance. The fixture
removed its containers, bounded exports/tmpfs mounts, network and data volume;
only the default Podman network and existing toolchain/registry cache volumes
remain. Images and NFS modules are retained. Validation used the Windows checkout,
healthy root Podman WSL2 engine and native container `/work` builds. Hard NFSv4.1
clients with `local_lock=none` shared kernel `6.18.33.2-microsoft-standard-WSL2`.
This does not qualify the old SLES kernel/hardware or independent-host fencing.
Cooperative exclusion passed; `protection_complete` and `production_authorized`
remain false. No failing gate or fixture run occurred in this increment.

Full rerun after both mandatory gates pass:

```text
python scripts/check-nfs-boundaries.py rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --isolated-startup --ownership --runtime --enrollment-storage --delivery-storage
```

Every Rust build/test uses cargo-zigbuild GNU/glibc 2.22, ELF audits and exact
target execution in pinned SLES 12 SP5 userspace.

Maintain SC-071/072 and DOC-01–05 in [the scenario catalog](RUST-SCENARIOS.md).
Keep the roadmap forward-looking. Broader retry classification/backoff, physical
storage/quota/EIO, in-flight RPCs, old-kernel/power-loss and independent fencing
remain future qualification; registration and offline repair remain deferred.
