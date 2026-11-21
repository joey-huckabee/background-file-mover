# Rust installation and deployment status

The application is implemented in Rust. Use these current sources:

- [Supported deployment and qualification matrix](SUPPORTED-DEPLOYMENT.md) (DOC-05).
- [Disconnected package production and guarded installation](OFFLINE-INSTALL.md).
- [Restart scenarios and surviving-worker handling](RUST-RESTART-RUNBOOK.md).
- [Release closure](RUST-RELEASE-CLOSURE.md) and
  [first-release scope](RUST-FIRST-RELEASE.md).

Read each source's implementation and qualification status. A proposed contract,
passing unit test or installation candidate is not production qualification.
All eight release gates remain open. Explicit offline migration and the
UUID/manifest-v2 runtime are implemented (increments 115 and 118). Production
NFS remains disabled; move mode and confirmed data deletion exist but are off
by default. See the [supported deployment matrix](SUPPORTED-DEPLOYMENT.md). No operational-state
conversion, repair, takeover or deployment is authorized by this documentation.
