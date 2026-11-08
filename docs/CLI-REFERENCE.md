# Rust command documentation

The application is implemented in Rust. Use these current sources:

- [Implemented operator commands and limitations](RUST-OPERATOR-GUIDE.md).
- [Guarded state inspection and backup](OFFLINE-STATE-BACKUP.md).
- [Release closure](RUST-RELEASE-CLOSURE.md) and
  [first-release scope](RUST-FIRST-RELEASE.md).

Read each source's implementation and qualification status. A proposed contract,
passing unit test or installation candidate is not production qualification.
All eight release gates remain open. Production NFS/source deletion, migration
apply and UUID/manifest-v2 activation remain disabled. No operational-state
conversion, repair, takeover or deployment is authorized by this documentation.
