# Increment 109: offline installation bundle

2026-11-03. The user authorizes producing an offline bundle and instructions
to build/install/use it. This packages the current Rust prototype without
freezing pending API behavior or approving production deployment.

## Scope

The builder accepts only a clean committed checkout and a passed, clean
production Cargo-libc/SLES report with matching pins and exact current Rust
source inventory. It rehashes retained artifacts, selects the release service,
verifies locked cached crate archives, collects license/source material and
produces a deterministic versioned tar.gz with internal/external checksums.
No images, crates or packages are downloaded. Rust toolchain notices are copied
from the exact cached builder image from the gate evidence.

The bundle contains an existing-OS dependency list, examples, documentation,
source/license material and a candidate native systemd template. No replacement
glibc, vendor RPMs, live config, state, credentials or enrollment is packaged.
The installer verifies twice and publishes only a new versioned code directory;
existing destinations refuse. No service/account/config/state/mount is created,
enabled, started, migrated or deleted by installation. Upgrades and compatible
binary rollback require explicit old-worker exit and original-state preservation.

The unit uses control-group termination, SendSIGKILL=no, no global ExecStop,
and explicit prototype activation (Restart=no). It is not the old C++ unit or
a qualified shipping lifecycle/account policy. Default TimeoutStopSec=75 is
documented against the application's default 60-second budget, with adjustment
required for a different configured budget.

## User and maintainer instructions

[Offline produce/install/use guide](OFFLINE-INSTALL.md) includes prerequisites,
trusted digest transfer, disconnected verification/installation, first-use
provisioning/enrollment boundaries, candidate unit activation and state-preserving
upgrade/recovery/removal. Existing restart and operator guides remain authoritative
for recorded jobs. Full tracked project source is included for offline references;
ignored historical raw packs stay outside the archive.

## Validation

Three Python regression methods pass on Windows before packaging. They cover
failed/qualification/unclean gate refusal, deterministic archive ordering/modes,
unsafe archive paths, missing/corrupt cached crates and license material collection.

The packaging checker writes a separate result for the exact archive, including
its SHA-256, pinned runtime, observed network and each executed check. Produce
and preserve that result alongside a delivered archive; do not infer success
from archive creation alone.
The reused executable comes from the passed offline production gate
20261103T131744Z-b9d8096d: 218 debug and 218 release tests; the matching offline
qualification gate passed 220 per profile. No Rust source/pins/dependencies change.
Packaging tests execute only the retained gated executable in pinned SLES userspace;
no host Cargo or new Rust build is used.

## Completed package validation

The final candidate is built from packaging commit `1214f3919ba1`; its retained
production executable still matches the original gate hash. The separate
[package evidence](OFFLINE-BUNDLE-EVIDENCE.json) records the exact archive name,
size/digest, two-build comparison and actual pinned-SLES installation result.
The checker passes offline verification/install/reverification, refusal of
existing/noncanonical/nested destinations, tampered/extra-file refusal, fresh
local enrollment, real HTTP submission, payload/manifest size/SHA-256 checks,
retained source and clean original-state restart/replay with an unchanged manifest.
UID/GID 1000, no capabilities, no-new-privileges and network=none are retained.
No live host service/account/config/state was changed.

The candidate unit passes syntax-only verification with systemd 255 on WSL.
This is not a lifecycle pass on that manager or exact SLES vendor qualification.
Shell syntax and three Python packaging regression methods pass on Windows/WSL
as applicable. No Rust rebuild is needed: complete retained gate source/pin and
artifact inventories match the unchanged Rust tree.

Keep preliminary failed reports. Initial assembly expected an absent plain-text
Rust COPYRIGHT; the collector was corrected to the cached HTML/license layout.
Preliminary checks exposed missing tar/awk in the minimal runtime, an unnecessary
chown under dropped capabilities and unavailable Bash /dev/tcp. The final checker
uses extracted-directory transfer, native minimal utilities, primary UID/GID 1000
and the image's existing Perl Socket fixture client. The service log and local
Running status identified the readiness probe error; no runtime check/assertion
or service behavior was relaxed. Earlier failed/passing candidate archive reports
remain ignored locally and are indexed in the tracked evidence.

All eight release gates remain open. This advances FR-06/RC-21, not complete
deployment/rollback/confinement or physical durability qualification. Production
NFS/source deletion/automatic cleanup/remote ingress remain disabled.
