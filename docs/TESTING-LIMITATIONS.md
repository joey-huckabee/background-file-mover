# Rust validation limits

The application is implemented in Rust. Use these current sources:

- [Eight open release gates](RUST-FIRST-RELEASE.md).
- [Finite acceptance matrix and unqualified obligations](RUST-RELEASE-CLOSURE.md).
- [Release closure](RUST-RELEASE-CLOSURE.md) and
  [first-release scope](RUST-FIRST-RELEASE.md).

Read each source's implementation and qualification status. A proposed contract,
passing unit test or installation candidate is not production qualification.
All eight release gates remain open. Explicit offline migration and UUID/manifest-v2
runtime are implemented in increments 115 and 118. Production NFS/source deletion
remain disabled. See [current release checks](RUST-INCREMENT-119.md) for evidence
and remaining blockers. No operational-state
conversion, repair, takeover or deployment is authorized by this documentation.
