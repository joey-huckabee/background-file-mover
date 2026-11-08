# Rust dependency qualification

The current pinned dependency/version graph and Tokio features are stored in
[scripts/rust-qualified-dependencies.json](../scripts/rust-qualified-dependencies.json),
with integrity dependencies in
[scripts/rust-integrity-dependencies.json](../scripts/rust-integrity-dependencies.json).
The values were extracted unchanged from previously qualified inputs; extraction
is not a new qualification result. Cargo.lock and selected-feature checks remain
mandatory in [the SLES gate](RUST-SLES-GATE.md).

Current exact-target gate evidence is recorded per implementation increment.
Use the named commits, source/artifact hashes and scope, including
[increment 112](RUST-INCREMENT-112.md). The source/tool cleanup in
[increment 114](RUST-INCREMENT-114.md) requires fresh applicable CI. It changes no
dependency version or feature selection. Historical comparison harnesses are
retired; their results are not relabeled as independent runtime qualification.

Preserve [the license policy](LICENSE-POLICY.md), offline package notices,
source hashing and pinned GNU/glibc-2.22 ABI/runtime checks.
