# Native HTTPS listener: finite real-service cases

Source `071523365d2bbac7b3a1344e3a52132a294f61fa`, Rust tree
`65a4ca5d2682b543ada306f2e5b720163f33afac`. Disposable local roots/state and
gate-generated certificates only. No operational service or credentials.

CI run42563593572 passes 286 production/290 qualification tests per debug/release
profile, including all nine TLS test functions. Native listener test source is
`rust/crates/file-mover/tests/tls_listener/mod.rs`. Both full local modes also
pass: production286 and qualification290 tests per debug/release profile, five
existing ignored cases each and clean cleanup. See increment123 and its
machine-readable evidence for report IDs/hashes and all 44 rehashed executables.
The client is Rustls/AWS-LC too; this is not independent-client interoperability.

The main native HTTPS test makes 30 fixed producer connections, with additional
private readiness/status polling excluded from that count:

| Real endpoint case | Fixed connections | Required observation |
|---|---:|---|
| Missing/untrusted/expired/wrong-purpose client in TLS1.2/1.3 | 8 | TLS exchange fails; timeout is failure, not refusal evidence |
| Valid same-CA unapproved leaf in both versions | 2 | Encrypted403, caller_not_authorized |
| Health, retention, status, resume, admin, query/trailing-path variants | 7 | Producer403 without state disclosure |
| Identity, Authorization, cookie and forwarding assertions | 6 | 400 before admission |
| Wrong submission method | 1 | 405 |
| Wrong Host authority | 1 | 400 |
| Wrong generator | 1 | 403 |
| Source outside configured scope | 1 | 403 |
| Approved TLS1.2 submission of two known nested payloads | 1 | 202; eventual stored commitment; correct destination bytes and manifest sizes/SHA256 |
| Reordered TLS1.3 replay before/after original-state restart | 2 | Same202; original claims, destinations and manifest bytes unchanged; replacement producer files preserved |

Other real-service cases verify credential-free HTTP submission plus producer-only
route separation; nine credential startup refusals preserving original SQLite and
source-marker bytes; nine invalid configurations refusing before guard/database/
socket/enrollment creation; and private health under two seconds plus local stop
under five seconds while six TCP clients leave TLS handshakes incomplete.
Eight safe-reader regressions cover ownership/modes, size, links, replacement and
descriptor inheritance. The full gate also retains all existing API/custody/
recovery tests, ELF controls, exact SLES execution and native compiler audit.

Retain initial strict-lint failures and the diagnostic7-pass/2-fail TLS run. The
latter omitted JSON Content-Type in the test client and correctly received415;
the client was fixed without changing server validation or weakening assertions.

Remaining proof obligations: live reload/revocation races, stronger CPU isolation
and sustained cryptographic load, independent-client interoperability, fresh
disconnected packaging and supported deployment. All eight release gates remain
open; no production NFS/deletion or deployment is authorized.
