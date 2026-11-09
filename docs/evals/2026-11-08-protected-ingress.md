# Protected ingress: actual endpoint evaluation

Scope: disposable pinned SLES12SP5/glibc2.22 containers, debug and release,
real kernel peer credentials. This evaluates the authorized P02 boundary;
it does not deploy a proxy or qualify production traffic. Final measured
results and report hashes are recorded in increment121 and its evidence file.

Local report `ingress-121-local-6.json` passes both profiles: 68 captured HTTP
requests, eleven unsafe-path cases per profile, clean cleanup. Captured request
count includes readiness/commit polling and is not a fixed test count. Debug
health/control take 0.01s each (combined load elapsed 0.02s); release takes
0.00s/0.01s (elapsed 0.01s). All slow reads time out, with complete fixtures
in 5.00-5.01s. Report SHA-256:
`c415caa71c08512c1490879f22dd6d01b80fca23c1f13a58f53c489872692e60`.

| Case at the actual endpoint | Required observation |
|---|---|
| Protected daemon listeners | No TCP listener; producer0660/operator0600 with exact owners |
| Configured proxy UID | Producer handoff202 and original job receipt |
| Unrelated UID, invalid HTTP | Immediate403 before HTTP read deadline |
| Root with producer group access |403; group access cannot replace peer UID |
| Foreign UID on private operator | Transport closes without operator JSON |
| Missing principal header |403 before body JSON parsing |
| Spoofed principal header |403 without replay disclosure |
| Body generator differs from trusted principal |403 without new allocation |
| Duplicate principal header |400 framing rejection |
| Producer health, job, retention and variant paths |403 with no recording disclosure |
| Producer GET on submission path |405 and Allow:POST |
| Producer submission on operator endpoint |404 existing local envelope |
| Duplicate length or transfer-encoding framing |400 |
| Over8192-byte header |431 |
| More64 headers |400 |
| Body length65537 |413 |
| All denied requests | No next job; retained count remains one |
| Submit without reading response | Durable whole-set custody; later exact202 replay |
| Destination and private claims | Known original input bytes and matching v2 sizes/SHA-256 |
| Reuse producer paths, reorder file list | Same receipt/manifest; replacement leaves and original custody unchanged |
| Six incomplete producer requests | Seventh429 with one-second retry guidance |
| Operator health plus independent control under load | Each below3s, both before5s producer read deadlines |
| Occupied producer/operator reads | Six producer408s plus operator408; fixture completion below9s |
| Clean stop/restart and replay | Endpoint cleanup; original receipt, enrollment and all bytes preserved |
| Existing regular/symlink/stale/live endpoint, either role | Refuse; preserve original inode, bytes and all SQLite/payload files |
| Missing/writable/symlink socket parent | Refuse before effects |
| Replace own live socket pathname | Preserve replacement and renamed original socket on stop |

Raw requests/replies and numeric identity/capability evidence are retained in the
checker JSON. Socket-name negatives include two roles and four name types plus
three parent cases per profile. No application account provisioning, operational
state, NFS or deletion is involved.

Assumptions and limits: kernel SO_PEERCRED is authoritative only for this host
and UID namespace; the configured proxy principal must come from the separate
future authenticated proxy deployment. Group permissions limit pathname access,
while the UID check still rejects group members and root. Host root/same-UID
hostile mutation is outside the supported trust model. The fixture proves local
API behavior, not TLS authentication, systemd lifecycle, NFS settlement, crash
repair, or customer traffic distributions. Production verification after a future
authorized deployment remains separate.

The coordinator implemented/integrated the transport and owns target validation;
one specialist authored only the driver/tests and the independent reviewer
checked bounded diffs. Concrete review findings and failed-run causes are retained
in increment121. No fixed improvement percentage or measured token/cloud cost is
claimed.
