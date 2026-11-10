# Independent HTTPS client evaluation

Qualified checker source `b97c4cac56e2802b44c3848f279f9c1bcd401918` uses the existing
Rust tree `51721ff716101ce89297a60561949e2023a6aa30`. Fresh disposable EC P-256
credentials and private source/state only. The separately pinned client image
runs curl 7.88.1/OpenSSL 3.0.22; the SLES12SP5 server uses glibc2.22 and the retained
production debug/release executables. No runtime/build dependency changes.

Both profiles pass 70 actual client operations each, with clean owned resource
cleanup. This is 140 operations: 78 curl and 62 OpenSSL CLI. Exact protocol flags
restrict 32 operations/profile to TLS1.2 and 38 to TLS1.3. The same OpenSSL TLS
backend serves both client frontends; the server is Rustls/AWS-LC.

| Family | Operations/profile | Required and observed result |
|---|---:|---|
| Initial server/client certificate boundary |28|Both clients and protocol versions; missing/untrusted/expired/wrong-purpose leaves fail TLS, same-CA unapproved leaves get403; wrong server name/trust fails verification |
| Discarded receipt and recovery |2|One verified OpenSSL submission discards HTTP stdout; private status confirms durable whole-set handoff, curl recovers original202 receipt |
| Path reuse, reordered replay and original-state restart |8|Both clients/protocols return the same job/UUID receipt and preserve new producer bytes, original claims/output, manifest and file identities |
| Producer-only authorization/routes |7|Known UUID with spoofed generator, reserved source scope or asserted identity header refuses; health/status/retention and wrong-method reads cannot gain producer privileges |
| Valid server/client-leaf and client-CA rotation |16|IPC v2 activation uses same PID:start, next generation and new policy hash; curl observes replacement server leaf; old approved leaf gets403, removed CA fails TLS, newly approved/trusted leaves replay safely |
| Invalid replacement |4|Bad PKCS8 replacement refuses; active generation/policy/server/client identity stays unchanged and both clients replay through the preserved policy |
| Replacement-policy restart |5|New PID:start loads the saved replacement policy; removed CA remains refused; both clients/protocols recover original receipt and data |

There are 25 HTTP202 replies, 15 HTTP denials, 29 TLS refusals and one deliberately
discarded application receipt per profile. Seven preservation stages compare
actual known payload bytes, manifest size/hash assertions, immutable manifest
bytes, original device/inode/size/type, reused producer bytes, enrollment and
retained-job count. These are equality assertions against known inputs, not a
snapshot of possibly incorrect output.

[The evidence](../NATIVE-TLS-CLIENT-EVIDENCE.json) contains the full public report,
source/build/client pins, 83 source hashes, both service executable identities,
case counts and failed development-run hashes. 22 portable tests include strict
parsers, output/time bounds, mixed/outgoing alert rejection, existing-report
refusal, private diagnostic-file status/bytes/mode and cleanup continuation after
a client-removal timeout. The full source/guide review is separate from execution;
raw local binary rehashing belongs to the coordinator.

The lost-receipt case discards HTTP stdout at the application boundary while
OpenSSL handles TLS. It is not a deterministic network outage or pre-admission
disconnect. Client timings include OCI exec overhead and do not prove realtime
latency or throughput. The private network has no host-published ports; both
containers run UID 1000:GID 1001 with zero capabilities and no-new-privileges.

Fresh handshakes are tested. Persisted TLS session resumption/0-RTT, future-valid
client leaves, server-CA rollover, other backend/legacy clients and every PKI
revocation mechanism remain unqualified. No offline installation, physical
SLES/kernel/systemd/NFS/FIPS or shipping approval is claimed. All eight FR gates
remain open. Required PR checks must pass before integration.
