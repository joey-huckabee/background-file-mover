# Increment 108: strict offline Cargo-libc validation

2026-11-03. The user asks to advance release work that needs no further product
decisions. This bounded build-tool change addresses cached-input-only validation
under FR-06/RC-21-22, without claiming portable disconnected packaging is done.

## Change

Previously, application compilation/testing already ran in network-disabled
containers, but every gate run created an online provisioner and ran locked
Cargo fetch there. A cached environment still took the online provisioning path.

`scripts/check-rust-sles.py --offline` now:

- Requires the recipe/config-specific cached builder, digest-pinned SLES image
  and existing `file-mover-cargo-registry` volume. Missing prerequisites fail
  with connected-preparation guidance, without image build/pull or empty-cache
  creation.
- Checks locked crate availability using `cargo fetch --offline --locked` in
  the network-disabled builder. Missing crate data remains an error; no online
  provisioner or retry fallback is created.
- Uses `--pull=never` for container creation. Both modes inspect the actual
  builder/runtime network configuration and refuse anything other than `none`.
- Records `offline` and observed `container_networks` in the normal report.
  Full dependency/features, formatting, Clippy, debug/release builds, cargo-libc
  inspection, independent ELF audits, six negative controls and relocated SLES
  execution remain mandatory.

The default connected-preparation path remains available. It still limits online
access to image/source provisioning. The existing WSL wrapper forwards the new
option unchanged. CI runs the extended Python safety checks before its normal
two-mode gates; it does not claim an offline run solely from that step.

No Rust source, Cargo.lock, dependency, compiler/provider pin, runtime behavior,
operational state or production enablement changes. The builder recipe/cache tag
is unchanged. No new tool installation is required on the prepared WSL host.

## Checks

`python -m unittest discover -s scripts -p test_rust_sles.py` passes on Windows
and native WSL: three methods, including five offline failure subcases. These
inject missing builder/runtime/registry/crates and a wrongly networked builder.
They verify failure reports, no image/source online fallback, no empty cache
creation and cleanup of the exact owned container after a late refusal.
Existing stdout/stderr configuration-stream regression checks remain passing.

Validated gate source: `4f346e78a40be27043d7e07b6e93d58b792ad57f`.
The [tracked evidence inventory](OFFLINE-BUILD-EVIDENCE.json) binds that source
to the reports, actual image identities, configuration/tool/package inventories
and retained executables. Raw packs stay ignored in the native WSL clone.

| Mode | Run | Result |
|---|---|---|
| Offline production | 20261103T131744Z-b9d8096d | PASSED: 218 debug / 218 release, no cleanup errors |
| Offline qualification | 20261103T134809Z-ff687b76-nfs-qualification | PASSED: 220 debug / 220 release, no cleanup errors |

These are real full-gate runs, separate from the Python orchestration checks.
Both report `offline: true` and actual builder/runtime network modes `none`.
Both passed all six audit negative controls. Each audited/relocated 20 executables;
all 40 retained hashes match their reports. Both source archives contain the same
63 inputs, independently matched to committed Git blobs. Gate/tooling input hashes
are recorded separately because they sit outside the Rust source archive.
All containers created by these runs were removed; caches were retained.
No failed or interrupted full-gate attempt occurred in this increment.

## User procedure and limits

See [strict offline validation](RUST-SLES-GATE.md#strict-offline-validation) for
commands and missing-cache handling. Provision the connected gate on an
authorized build host before disconnecting, then use both offline modes
sequentially in the same prepared Podman storage.

This does not disable the host's network globally, export/import caches, or
provide an installable disconnected release bundle. Debian package repositories
remain unsnapshotted; exact image/package evidence identifies the cached builder.
The provider's observed non-PIE executable strategy remains a shipping-hardening
limitation. Remote ingress, admin/API work, source cleanup, production NFS,
deployment/rollback and all eight release gates retain their existing status.
No new NFS, systemd, physical-durability or runtime fault qualification is claimed.
