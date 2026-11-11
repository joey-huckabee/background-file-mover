# Admin password foundation: evaluation

This evaluates the approved dependency/verifier slice, not a working account,
HTTP login, session manager or scheduler integration. Implementation and final
results are [increment 127](../RUST-INCREMENT-127.md). The
[admin design](../dashboard/ADMIN-SESSION-DESIGN.md) retains the later proof matrix.

## Cases

| Test | Required outcome |
|---|---|
| RFC9106 §5.3 Argon2id known answer | Exact published 32-byte tag with RFC test parameters/secret/associated data; these parameters are not accepted by the production verifier wrapper |
| Exact UTF-8 input | Byte bounds, invalid UTF-8 refusal, no whitespace trimming or Unicode normalization; wrong assertion does not authenticate |
| Round-trip / wrong password / independent salts | Serialized verifier reopens, correct password verifies, wrong password fails and independent OS salts differ |
| Hostile verifier record | Algorithm/version/cost/order/unknown parameter, oversized record, salt and output encoding refusals happen before expensive verification |
| Entropy failure | No verifier returned; static error contains no secret |
| Maximum password | 4096-byte input is accepted for hashing; changing the final byte fails verification rather than matching a truncated prefix |
| Cost observation | Fixed m19456/t2/p1 hash/verify completes in the pinned SLES userspace; record milliseconds and kernel process VmHWM without a fabricated latency/availability pass threshold |

Seven new Rust tests execute in both target profiles. Current selected features
are enforced by the password feature map; historical per-package feature arrays
are not used to authorize the graph. Existing versions/checksums are preserved.

## Reproduce

On the existing connected/cached Linux qualification host, use the normal gates:

```sh
python3 scripts/check-rust-sles.py
python3 scripts/check-rust-sles.py --qualification
```

Do not replace these with host-native Cargo tests. Each full mode includes
debug/release, GNU/glibc2.22 preparation, ELF audits and pinned SLES execution.
`--offline` additionally requires every pinned image and locked source in cache.
No compiler, Cargo, package manager, OpenSSL upgrade or Python is added to the
disconnected production server by this password-library change.

For an isolated observation, choose the file-mover **library test executable**
from a PASSED production gate whose `.test` log lists
`password::tests::measured_fixed_profile_hash_and_verify`. The other file-mover
test executable can have zero tests. Recheck its hash against `report.json`.
Run that exact executable in the gate's digest-pinned SLES image, with network
disabled, capabilities dropped, no-new-privileges and UID1000:GID1001. Copy it as
`/proof` into the disposable container, then invoke:

```text
/proof --exact password::tests::measured_fixed_profile_hash_and_verify --nocapture --test-threads=1
```

Set `LD_BIND_NOW=1` as in the gate, capture the actual process exit status and
require one passed test and both `ADMIN_PASSWORD_PROOF` and
`ADMIN_PASSWORD_PROCESS_HIGH_WATER` lines. Remove only that owned container and
record its cleanup result. This filtered rerun is a cost observation using an
already qualified artifact; it does not replace either full mode.

## Interpretation

The isolated run includes password-owner construction, provider initialization,
salt generation, PHC formatting/validation and verification. Hash time is not
pure Argon2 CPU time. VmHWM includes the entire test process/provider, not only
the algorithm's memory blocks. One observation per profile is not a statistical
benchmark, maximum memory guarantee, CPU quota or realtime deadline proof.

Actual HTTP login/throttling, guarded account publication, global revocation,
non-yielding verifier shutdown ownership and control responsiveness remain later
integration acceptance work. No production credential or state is used. All eight
FR release gates remain open; this evidence cannot authorize deployment.
