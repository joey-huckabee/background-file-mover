# Native TLS resource isolation: finite service evaluation

Implementation results remain NOT_RUN. Disposable local roots/state and fresh
gate certificates only. Tests use Rustls/AWS-LC clients; independent-client
interoperability and shipping are separate. No production traffic is measured.

| Family | Real-service cases | Required observation |
|---|---:|---|
| Mixed certificate/protocol load | 24 connections in four six-peer waves | TLS1.2/1.3 approved/unapproved/missing/untrusted/expired/wrong-usage peers get bounded denials; private health under2seconds |
| Full encrypted JSON body | 1 exact65,536-byte padded valid submission | 202, measured payload integrity, eventual commitment |
| Body over limit | 1 declared65,537-byte header-only request | Early413, no body read/new work |
| Fragmented oversized handshake | 4 raw two-record messages | 65,536-byte handshake length refuses promptly; no HTTP or new jobs; timeout never counts as refusal |
| Slow HTTP after completed TLS | 6 simultaneous peers | Each408 under unchanged5-second server read deadline; seven-second client observation budget, cohort under8seconds |
| Non-reading peer | 1 small forbidden-route response | Control progress while peer does not read; eventual403. This does not claim saturation of OS send buffers |
| Both TLS workers consume CPU (qualification) | 2 held registered sessions,4 accepted queued ClientHellos,6 excess peers | Two distinct actual TIDs gain CPU ticks; private health/status/TLS-status respond under2seconds; excess closes; after6seconds queued expiration emits no TLS bytes |
| Reload while both workers stalled (qualification) | 2 registered sessions and2 raw queued connections | New policy activates but ACK waits for physical old-session exit; raw queued peers select replacement server leaf and old leaf gets403; newly approved peer succeeds |
| Shutdown beyond first deadline (qualification) | 2 non-yielding CPU workers | CLI reports ShutdownIncomplete/exit2; duplicate stop/config change cannot renew deadline; competing guard refuses until actual exit; original producer files stay untouched |

Unit cases cover six-job admission, immediate completions, main-reactor scheduling,
actual future-destructor/guard lifetime, panic fail-closed, stopping/startup and
simulated second-thread startup failure. Simulation is not evidence of a physical
OS thread-creation failure. CPU checkpoint is production-inert and not a literal
malicious certificate workload; real handshake waves exercise actual cryptography.

No hard OS quota, reserved CPU core or realtime latency guarantee is claimed.
A before/after malicious CPU workload against an operational predecessor is not
available/authorized. Pinned source explains its shared executor; actual endpoint
post-change observations and deterministic non-yielding cases establish only the
recorded development bound. Both full SLES modes, source/artifact audits, independent
review and final PR CI remain pending before integration.
