# E3: serde and serde_json compatibility

Run `python experiments/e3-json/run.py` from the repository with Podman on
PATH. It builds on modern Linux using the pinned cargo-zigbuild reference,
installs Rust 1.99.0, targets GNU/glibc 2.22 with baseline x86-64 CPU settings,
and tests the binaries in pinned SLES 12 SP5 userspace. It removes its created
containers and keeps logs, ELF reports, source/vendor archives and binaries
under ignored `results/<run-id>/`.

The workspace contains a std control, a serde/serde_json probe, and a cumulative
probe adding E1 SQLite and E2 rustix. The only selected JSON features are
serde `std,derive` and serde_json `std`. Cargo.lock pins resolved versions.
The harness records host procedural-macro packages separately, audits the
actual target executables and runs six negative ELF audit controls.

The C++ parser is compiled only as a build-host corpus oracle. The 38 committed
corpus files are preserved exactly and compared by actual parse outcome rather
than inferred filename. Explicit byte tests cover misleading seed names.
The Rust adapter enforces ADR-0009's object-only, integer-only, no-null/no-NUL,
duplicate-free profile and the C++ default limits (depth 4, input 65536 bytes,
string 4096 bytes, object/array 64 members/elements). A lexical integer-policy
guard allows integer `-0` while rejecting decimal and exponent spellings.
Serde handles syntax and encoding. Input is capped before decoding; decoded
string/key limits are checked by the visitor, so escaped-token scratch
allocation is bounded by the overall input cap rather than the string cap.

Tests cover typed request decoding/serialization, whole input, signed int64,
Unicode/control roundtrips, limits and 10000 deterministic corpus mutations.
All repeat in cumulative rename and link/unlink modes with a local SQLite DB.
This is package qualification, not the final service JSON module or complete
differential fuzzing. The fixture uses the WSL2 kernel and does not execute an
old kernel/CPU. No NFS fixture is needed for JSON; its retained setup is in
[the NFS note](../../docs/NFS-TEST-FIXTURE.md).

`--reuse-build <run-id>` reruns runtime and audit checks only after verifying
the retained source archive against current probe, corpus and C++ oracle inputs
and the pinned image configuration. Any source/dependency change needs a fresh
build. Complete compatibility must be rechecked on compiler/builder changes.
