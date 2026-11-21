# Rust operator documentation

The application is implemented in Rust. Use these current sources:

- [Producer quickstart and retry decision table](PRODUCER-QUICKSTART.md)
  (DOC-01): how a recorder submits files and handles every reply.
- [Consumer guide](CONSUMER-GUIDE.md) (DOC-02): the destination layout, when a
  recording is complete and how to check it against its manifest.
- [Implemented behavior and operator actions](RUST-OPERATOR-GUIDE.md).
- [Restart and shutdown recovery runbook](RUST-RESTART-RUNBOOK.md) (DOC-04).
- [Supported deployment and qualification matrix](SUPPORTED-DEPLOYMENT.md) (DOC-05).
- [Stable user situations, evidence and limits](RUST-SCENARIOS.md).
- [Release closure](RUST-RELEASE-CLOSURE.md) and
  [first-release scope](RUST-FIRST-RELEASE.md).

Read each source's implementation and qualification status. A proposed contract,
passing unit test or installation candidate is not production qualification.
All eight release gates remain open. Explicit offline migration and the
UUID/manifest-v2 runtime are implemented (increments 115 and 118). Production
NFS remains disabled; move mode and confirmed data deletion exist but are off
by default. See the [supported deployment matrix](SUPPORTED-DEPLOYMENT.md). No operational-state
conversion, repair, takeover or deployment is authorized by this documentation.
