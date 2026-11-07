# Rust increment 29: real NFS enrollment space exhaustion

Increment on `feature/rust-transfer-coordinator`, 2026-10-15. Extends the
qualification from [increment 28](RUST-INCREMENT-28.md) to actual server ENOSPC
responses. The service implementation, Rust inputs/dependencies, public API,
schema 10, binding version 3 and receipt format are unchanged. Production NFS
and source deletion remain disabled. No enrollment repair or takeover is added.

## Selected cases and intended behavior

The retained fixture gains an opt-in `--enrollment-storage` mode and
`scripts/nfs_storage.py`. It exports a separate server tmpfs limited to 4 MiB
and 128 inodes with an explicit filesystem ID, mounted by the pinned SLES client
using hard NFSv4.1. Filler files live only in that bounded disposable mount;
the host filesystem is never filled. This is real server filesystem exhaustion
through NFS, not an application-injected errno. A tmpfs is not a physical disk
or a power-loss durability model. See [kernel tmpfs documentation](https://kernel.org/doc/html/v6.10/filesystems/tmpfs.html)
and [export configuration](https://www.man7.org/linux/man-pages/man5/exports.5.html).

Each debug/release profile exercises two fresh source scopes:

- Exhaust inodes after provisioning. Initialization must fail with ENOSPC and
  preserve prepared local ownership without creating a receipt. Ordinary startup
  remains pending. After freeing only the fixture filler, explicit initialization
  with the same database may create/sync the receipt, activate and reach readiness.
- Exhaust data blocks after provisioning. Initialization must fail without
  activation. Any created receipt must remain preserved for review. Freeing space
  does not authorize adoption or overwriting of that created object; explicit
  retry must still refuse and retain the same pending evidence.

Both cases require a known enrollment-stage diagnostic, unchanged producer data,
binding and lock, zero accepted jobs and an intact local database. State inspection
copies the stopped service's whole state directory, including any WAL, then uses
Python SQLite read-only against that copy. This inspection is not a build or a
replacement for the bundled SQLite/SLES execution gate. Producer data stays on
the NFS mount; the database stays on local storage. Fault selectors and worker
pause controls are not used in these cases.

The option also retains the six directional delivery baselines, production-NFS
refusals, OS inherited-lock/interrupted-metadata probes and isolated startup
shutdown checks. Existing `--ownership` and `--runtime` modes remain available;
the report must say which were actually requested. Do not describe this focused
storage run as a new full runtime/ownership regression.

## Validation

Production gate `20261015T223307Z-f161c275` PASSED 152 tests per debug/release
profile. Qualification gate `20261015T223308Z-69cd89a4-nfs-qualification` PASSED
153 per profile. Both passed formatting/Clippy, all 20 executable audits per mode,
six negative ELF controls and exact pinned SLES target execution. The external
dependency graph remains 42 packages; highest required GLIBC remains 2.18.
Verified both archive hashes and complete 53-file inventories/content against the
current unchanged Rust tree. See [production evidence](RUST-SLES-EVIDENCE.json)
and [qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).
All 20 artifact hashes per mode also equal increment 28's corresponding artifacts.

Focused NFS run `nfs-20261015T224853Z-d63a88e0` PASSED with exit status 0 and
`cleanup_errors: []`. All four storage cases and six directional delivery
baselines passed, along with production refusal, OS inherited-lock/interrupted
metadata and isolated startup shutdown controls. Inode exhaustion returned
`create_receipt: errno=28` with no receipt, then explicit retry activated and
served health successfully after capacity restoration. Data-space exhaustion
returned `create_receipt: enrollment_write errno=28`, left ownership prepared,
and refused retry after freeing space while preserving the original receipt.
All cases retained original producer data, binding/lock evidence and zero jobs.
See [full focused report](RUST-NFS-ENROLLMENT-SPACE-EVIDENCE.json).

Immediately after the failed block writes, client metadata reported 456 bytes
(debug) and 458 bytes (release); its read hash matched that many zero bytes.
The server reported a zero-byte receipt. After capacity restoration, client and
server views both showed zero bytes, with the same respective inode/owner/mode
identities. Both size/hash views then remained unchanged across refused retry.
These are observed views in this run, not a required cache behavior on other
kernels. They reinforce that a failed write's pathname, size or client read alone
cannot establish durable enrollment.

The three storage-driver hashes and exact artifact hashes match the saved report.
Fixture-owned containers, exports, tmpfs, network and data volume were removed;
only the default Podman network and existing toolchain/registry cache volumes
remain. Cached images/modules are retained. Validation used the Windows checkout
and healthy root Podman WSL2 engine, with native container `/work` builds.
The kernel was `6.18.33.2-microsoft-standard-WSL2`. This run did not request
`--ownership` or `--runtime`; retain [increment 28's full regression](RUST-INCREMENT-28.md)
as the separate unchanged-service runtime/ownership evidence.

Reproduce the focused run after both mandatory gates pass:

```text
python scripts/check-nfs-boundaries.py rust/validation/<production-run> --qualification-gate rust/validation/<qualification-run> --isolated-startup --enrollment-storage
```

First run `nfs-20261015T224231Z-5df606ee` FAILED with `cleanup_errors: []`.
Debug inode exhaustion passed, including original-state retry/readiness. Debug
block exhaustion returned `create_receipt: enrollment_write errno=28`, left local
ownership prepared and created a receipt, but the fixture incorrectly assumed
the failed write implied a zero-length client view. That size assertion failed.
The revised fixture records client and server size/hash views at the error and
after capacity restoration, requires unchanged object identity, then requires
each view and pending state unchanged across refused explicit retry. A failed
NFS write does not establish empty content or authorize adoption. No service
implementation change was made, and the failed report remains failed evidence.
Its source gates remain valid because only the Python assertion changed.

Every Rust build/test continues through the GNU/glibc 2.22 cargo-zigbuild gate,
ELF audits and exact debug/release target execution in pinned SLES 12 SP5
userspace. This fixture uses a modern shared WSL2 kernel and selected tmpfs
exhaustion; it does not qualify old kernels/hardware, server reboot, disk EIO,
in-flight synchronization outages, partitions/reclaim or independent fencing.

Maintain SC-068/070, the SC-047 boundary and DOC-03–05 in
[the scenario catalog](RUST-SCENARIOS.md). Actual server disk exhaustion during
payload copying, physical free-space margins and deletion remain separate work.
