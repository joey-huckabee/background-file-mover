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
Initial target attempt stopped at formatting before compilation; it is not a
qualification pass. Fresh full production and qualification results remain
pending until recorded here. No SLES compatibility or shipping claim is made
from Cargo metadata, source review or the library's Rust minimum version.

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
