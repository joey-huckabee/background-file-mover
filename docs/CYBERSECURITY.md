# Rust security and ownership boundaries

The application is implemented in Rust. Use these current sources:

- [Provisioned roots, original-state custody and exclusion](ROOT-OWNERSHIP-DESIGN.md).
- [Proposed producer ingress boundary](REMOTE-API-ACCESS-CONTRACT.md).
- [Release closure](RUST-RELEASE-CLOSURE.md) and
  [first-release scope](RUST-FIRST-RELEASE.md).

Read each source's implementation and qualification status. A proposed contract,
passing unit test or installation candidate is not production qualification.
All eight release gates remain open. Production NFS/source deletion, migration
apply and UUID/manifest-v2 activation remain disabled. No operational-state
conversion, repair, takeover or deployment is authorized by this documentation.
