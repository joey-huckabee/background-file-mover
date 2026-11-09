# Live TLS reload: finite service and race evaluation

Disposable local roots/state and gate-generated certificates only. No real keys,
operational state or NFS. Source `99474cd2c290256b3ea385ae28ae7cc05bd7790a`, Rust tree
`8ee490b0f2c3bd013c1b957d4a616e70d326f274`. Both full local modes and source CI
pass 301 production/305 qualification tests per debug/release profile, with clean
cleanup. All 13 TLS functions pass in each profile; both pause race bodies execute
in qualification. See [increment124](../RUST-INCREMENT-124.md) and its
[machine-readable evidence](../NATIVE-TLS-RELOAD-EVIDENCE.json) for exact reports,
source/pin hashes and all 44 independently rehashed local executables.
The TLS client uses Rustls/AWS-LC too; independent-client interoperability remains
separate. Keep all assertions and existing timing/ELF/native compiler controls.

| Case | Required observation |
|---|---|
| Rotate server leaf/key and approved same-CA client | Generation advances, full public policy hash changes, server leaf hash matches replacement, PID:start unchanged |
| Incomplete handshake and established idle old TLS connection | Transport reaches EOF/reset before reload success; timeout never counts as refusal |
| Removed approved client from unchanged trusted CA | New connection returns403; new approved client replays the original202 |
| Replace client trust root | Former CA client fails TLS; newly approved other-CA client succeeds using TLS1.2 |
| UUID and file integrity through both rotations | Exact original202, manifest bytes, known private-claim/destination bytes and retained-job count preserved |
| Five invalid replacement proposals | Missing key, changed nonTLS setting, changed authority, mismatched key and new credential directory all fail; generation/hash unchanged and an existing TLS connection still works |
| Actual admitted claim paused, second request queued (qualification) | Status shows both states; reload acknowledges and closes queued connection before releasing the admitted claim; admitted request completes202; second producer file untouched and no second job |
| Loader paused after validation (qualification) | TLS status and operator health respond, busy second reload refuses; stop wins before activation, generation stays1, loader exits before guard can be reacquired |
| Activation before first connection-future poll | Unit regression observes initial generation mismatch and removes registration before ACK |
| Session exits while stale Work remains | Unit regression proves queued lease does not retain connection registry and cannot admit after reload |
| Admitted attempt defers for source space | Unit regression resets admission; old lease cannot requeue after activation |
| Certificate expiry at admission | Unit regression uses an explicit future verification time with real certificate validation; does not change host clock or add a runtime clock override |
| Mounted endpoint | Proc-metadata exclusion rejects the complete individually mounted OCI file; reserved reload control name cannot become the SQLite database |

The qualification checkpoint is production-inert and uses disposable rendezvous
files. It proves local ordering/responsiveness, not physical uninterruptible I/O.
The existing nine TLS functions and complete API/custody/recovery suites remain
part of both full gates. Two qualification-only integration bodies return without
executing their pause in production; production counters alone must not be
presented as execution of those race scenarios.
