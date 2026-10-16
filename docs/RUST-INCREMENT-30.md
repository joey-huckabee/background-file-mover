# Rust increment 30: destination-full copying and audited recovery

Increment on `feature/rust-transfer-coordinator`, 2026-10-15. Extends
[increment 29](RUST-INCREMENT-29.md) from enrollment metadata to payload delivery.
The Rust implementation, dependencies, public contract, schema 10, binding
version 3 and receipt formats are unchanged. Production NFS and source deletion
remain disabled. No repair, cleanup or takeover capability is added.

## Selected user situation and fixture

The retained NFS runner gains `--delivery-storage`, backed by
`scripts/nfs_delivery_storage.py`. A separate server tmpfs is capped at 32 MiB
and 512 inodes, exported with its own filesystem ID and mounted as hard NFSv4.1
by the pinned SLES client. Only fixed fixture filler files are removed; the host
filesystem is never filled. Sources and SQLite stay on protected local storage.
Both debug and release use exact audited qualification executables.

Each profile has a live-recovery and an original-state restart case:

1. Provision source/destination bindings, explicitly initialize the source and
   start normally. Create a 2 MiB plus 17-byte payload with known nonzero content.
2. Fill only the bounded server export until ENOSPC, then shrink its filler to
   leave 1 MiB free. Submit the file without a size assertion. Require HTTP 202,
   durable claim custody and permitted producer-path reuse.
3. Let actual copying consume the remaining capacity. Require partial staging on
   the server, matching source prefix data, retained original claimed source,
   no final payload/manifest and responsive health/status. The existing three
   failed delivery attempts must reach durable review without commitment.
4. In the restart case, stop/restart against the original configuration and
   database while still full. Review status and original staging must survive.
5. Remove only the filler. Capacity restoration must not clear review. Use the
   existing audited resume request with its current epoch; repeat the same command
   to confirm replay. Do not modify state or staging to make recovery succeed.
6. Require the same job to commit on a new copy attempt, preserve old partial
   attempts, verify full source/client/server destination hashes and exact manifest
   content, and retain the producer's new file at the reused path. The restart
   case also checks committed status/manifest after another original-state restart.

No application fault selector, pause rendezvous, manual receipt repair or database
mutation is used. Health/status sample durations include host engine/transport
overhead and must remain within the selected 15-second fixture window; this is
not a production latency SLO or continuous saturation/memory qualification.

The current payload error diagnostic can be generic (`blocked_or_uncertain`),
unlike enrollment's explicit write errno. The fixture records service logs and
measured server capacity/partial contents. Do not describe a generic worker error
as an errno-specific service response. Better retry classification/backoff and
payload diagnostics remain future work; review/resume does not bypass normal
custody, destination binding, hashing, verification or no-clobber publication.

## Validation

Production gate `20261016T003846Z-09b7dc3d` PASSED 152 tests per debug/release
profile. Qualification gate `20261016T003847Z-be3ef32f-nfs-qualification` PASSED
153 per profile. Both passed formatting/Clippy, all 20 executable audits per mode,
six negative ELF controls and exact target execution in pinned SLES userspace.
The external graph remains 42 packages and highest required GLIBC remains 2.18.
Verified each source archive hash and complete 53-file source inventory/content
against the unchanged Rust tree. All 20 artifact hashes per mode equal increment
29's corresponding artifacts (and thus the unchanged-service increment 28 full
runtime artifacts). See [production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

Combined storage run `nfs-20261016T004810Z-270ebf6e` PASSED with exit status 0
and `cleanup_errors: []`. All six directional delivery baselines, four enrollment
ENOSPC cases and four destination-full delivery cases passed. Production NFS
refusals, inherited OS lock/interrupted metadata and isolated bootstrap shutdown
controls also passed. See [the complete combined report](RUST-NFS-DELIVERY-SPACE-EVIDENCE.json).

Each new case returned HTTP 202/Claimed, preserved the original source inode/data
and allowed the producer to write a new file at its old path. The server retained
exactly 1 MiB of the known `A` prefix in attempt 1 while its data capacity reached
zero. Three failed attempts reached durable ReviewRequired with transfer Intent.
The generic worker log was `blocked_or_uncertain`, with persistent
`delivery_requires_review`; no errno-specific service response is claimed.
Restoring capacity alone left review and old partials unchanged.

Audited resume and exact command replay succeeded. The original job committed
on attempt 4 without replacing old partials, and source/client/server payload
hashes and exact completion-manifest contents matched. The recorder's newly
written file survived and submission replay returned the same job ID/202.
Live cases kept the same coordinator throughout recovery. Restart cases retained
review/status/partial evidence across the first original-state restart and
committed status/manifest across the second. Every sampled health/status pair
completed within 3.422 seconds including host engine/transport overhead, below
the selected 15-second fixture window.

Driver/artifact hashes match their saved evidence. The fixture removed its
containers, bounded exports/tmpfs mounts, network and data volume. Only the
default Podman network and the two existing toolchain/registry cache volumes
remain; images/modules are retained. Validation used the Windows checkout and
healthy root Podman WSL2 engine, native container `/work` builds and kernel
`6.18.33.2-microsoft-standard-WSL2`. No failing gate or fixture run occurred in
this increment.

Reproduce after both mandatory gates pass:

```text
python scripts/check-nfs-boundaries.py rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --isolated-startup --enrollment-storage --delivery-storage
```

This focused command did not request the separate full `--runtime`/`--ownership`
suites. Keep [increment 28's full regression](RUST-INCREMENT-28.md) as separate
evidence for those unchanged, byte-identical service artifacts; do not infer a
new full regression from the focused storage report.

Containers use SLES 12 SP5/glibc 2.22 userspace on the modern runner kernel.
Bounded tmpfs exhaustion is not physical-disk/quota, hardware EIO, power-loss,
partition/reclaim, lost-lock or independent-fencing qualification. Keep the
permanent qualification feature/fixtures. Maintain SC-071, SC-047 and DOC-01–05
in [the scenario catalog](RUST-SCENARIOS.md); broader retry classification,
free-space margins and production NFS prerequisites remain future work.
