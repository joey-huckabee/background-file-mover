# Increment 127: approved password verifier foundation

The user approves adding the Argon2id packages and proceeding with the
[admin implementation design](dashboard/ADMIN-SESSION-DESIGN.md). This first
bounded implementation slice adds the password primitive and target proof.
It does not activate a listener, account file, provisioning command, login,
session or browser-to-service connection.

## Implemented scope

- Pin argon2 0.5.3 (`std,zeroize`, default features disabled) and the four approved
  supporting packages: base64ct 1.8.3, blake2 0.10.6, password-hash 0.5.0 and
  rand_core 0.6.4. Preserve all existing versions/checksums. Add direct zeroize
  use at its existing 1.9.1 version; subtle remains a library dependency.
- Pin selected password/shared features in the existing SLES gate, including
  digest MAC/subtle and getrandom/std. Expected graph is now resolved, not only
  a metadata proposal. No ring provider or system OpenSSL dependency is added.
  `password_selected_features` is the current enforced feature map; older
  per-package `dependencies[].features` arrays are retained metadata snapshots,
  not the feature-selection gate. In particular the historical getrandom entry
  has an empty array, while its newly enforced selected features are `std`.
- Add `file_mover::password`, a synchronous helper for later owned-worker use.
  Password buffers and stored PHC strings have explicit zeroizing ownership and
  no Debug/Display/Serialize/Clone. This is not guaranteed memory erasure of all
  potential future caller/HTTP copies.
- Enforce exact valid UTF-8 passwords of 1–4096 bytes and usernames of 1–128
  bytes without trimming/normalization. Use the existing crypto provider for
  salt entropy. Fail closed on entropy error.
- Admit only canonical Argon2id v19, m19456/t2/p1, 16-byte salt and 32-byte tag,
  within a 256-byte PHC limit. Refuse foreign/huge cost before hashing. Verify
  using the library's constant-time comparison; wrong password is distinct from
  malformed verifier/error, without exposing secret values in error messages.
- Include the RFC9106 section 5.3 library known answer, round-trip/wrong-password
  checks, Unicode/bounds/no-truncation cases, hostile PHC and entropy failure.
  Cost observations record hash/verify time and process VmHWM; they are not
  per-allocation measurements or control responsiveness/CPU-quota proof.

## Validation status

Independent review at b4a904f found no actionable source findings. The subsequent
4cdd2f0 changes only formatting. Five portable SLES-gate safety tests pass.
The initial local attempt and CI at 4cdd2f0 stopped at formatting before
compilation; neither is a qualification pass. CI also caught a coordinator/WSL
module-order mismatch. It was fixed in d57f974. Independent byte comparison
confirms all 84 archived local Rust inputs equal the final committed tree;
qualification is credited to actual inputs, not an assumed clean initial checkout.

The retained local full production gate `20261111T032524Z-705753ec` passes **322
tests per debug/release profile**, with 22 executable hashes and ELF records
independently rechecked, both native compiler audits reproduced and clean cleanup.
PR19 CI run `42953018873` passes both full modes: production **322/profile** and
qualification **326/profile**. Its production job additionally passes protected
ingress and all **140 independent TLS client operations**. Downloaded reports,
84 production Rust input hashes, synthetic checkout tree and all four CI native
compiler audits were checked. The required qualification mode was exercised in
CI; it was not redundantly rerun locally. CI executable bytes were not uploaded
for independent rehash; the retained local executables were rehashed.

[Machine-readable evidence](ADMIN-PASSWORD-EVIDENCE.json) records exact inputs,
pins/features, test reports, artifacts, source hashes, the measurement driver, advisory
snapshot and failed attempts. The CI checkout commit differs from the branch
head but its whole tree equals source head d8b2c4b. Documentation closeout changes
no Rust/build/gate inputs. Target evidence is container SLES userspace against
glibc2.22, not physical kernel/NFS/systemd/FIPS or a shipping qualification.

| Isolated process observation | Debug | Release |
|---|---:|---:|
| Hash including initial provider/input work | 796 ms | 112 ms |
| Hash plus verification path | 1523 ms | 163 ms |
| Kernel process VmHWM | 25920 kB | 23888 kB |

Each is one fresh UID1000:GID1001 SLES test process with exact executable hash,
network disabled, zero effective capabilities, no-new-privileges and cleanup
exit 0. These are observations, not a latency limit, per-allocation memory or
control responsiveness proof. See the [evaluation/reproduction notes](evals/2026-11-10-admin-password-proof.md).
No credentials or private TLS/session material appear in the public evidence.

Bounded upstream RustSec review at database commit
`28d73fc95e5972af3403225a217def57dcaba3c4` checked the five new package names and
affected shared digest/getrandom/subtle/zeroize names. The three returned records
are RUSTSEC-2019-0019 (blake2, patched >=0.8.1), RUSTSEC-2019-0035 (rand_core,
patched >=0.4.2) and RUSTSEC-2021-0023 (rand_core, patched >=0.6.2). Selected
blake2 0.10.6 and rand_core 0.6.4 satisfy these patched ranges. No applicable
record was identified in that bounded snapshot; this is not a complete lockfile
audit or assurance against unpublished issues. See the
[RustSec database](https://github.com/RustSec/advisory-db/tree/28d73fc95e5972af3403225a217def57dcaba3c4).

## Next integration and limits

The next account/session slice must own verifier execution on a bounded worker,
keep instance ownership through actual exit, implement guarded local credential
publication/activation and global revocation admission, and prove control
responsiveness. These obligations are not delivered by a callable helper.
No real account/credential/state operation, dependency installation on the target,
deployment, production NFS/deletion or full release is introduced. All eight FR
gates remain open. The frontend remains plain offline HTML/CSS/JavaScript with
original SVG icons and no build/package dependency.
