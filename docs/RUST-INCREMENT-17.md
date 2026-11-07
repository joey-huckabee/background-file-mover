# Increment 17: Owned no-clobber relocation fallback

The [diagnostic baseline](RUST-NFS-DIAGNOSTIC-EVIDENCE.json)
`nfs-20261014T115111Z-cd0adc32` confirmed errno 22
(`EINVAL`) from `claim.rename_noreplace` and `publish.rename_noreplace`, in both
profiles. All six cases remained blocked with retained data and no manifest.
Its source binaries passed production gate `20261014T112710Z-674d976e` and
qualification gate `20261014T112710Z-16604e26-nfs-qualification`. This identifies
the failing operations on this fixture; it is not a claim about every NFS server.

Private worker failures now retain bounded operation/errno or static custody
details. Diagnostics are limited to 240 printable ASCII bytes, cannot accompany
a successful effect receipt, and do not authorize state transitions or prove an
effect was not applied. Arbitrary error strings, file paths and payloads are not
echoed. Claim custody checks before/after an effect also return typed failures.

Claims, file publication and manifest publication share an owned regular-file
relocation helper. Native no-clobber rename remains the first choice. Only
`ENOSYS`, `EOPNOTSUPP` and `EINVAL` permit an exclusive hard-link fallback after
same-device and exact one-link identity checks. Other rename errors retain the
original and remain blocked/uncertain. No ordinary overwriting rename is used.

The fallback establishes the new link, validates the two exact name bindings,
synchronizes the object and new parent, then rechecks both bindings before
unlinking and synchronizing the old parent. A crash with both names present can
be reconciled only when both match the existing durable intent, including device,
inode, uid, size and modification time, with exactly two links. A third link,
foreign collision, changed object or uncertain lookup blocks reconciliation.
Normal source/copy/verification checks still require one link. A recovered final
file is reread and hashed; normal relocation adds no payload read to the 3N path.

The existing claim, publication and manifest intents remain authoritative; no
new intent is invented from an existing name. Link/unlink substeps are recognized
from the exact recorded object and name bindings under protected, fenced parents.
The producer must keep files untouched until 202. These rules do not establish
cross-client NFS fencing or stable export authorization.

New tests exercise unsupported syscall results, refusal of other errors, foreign
collisions and extra links, actual subprocess exits at four link/unlink boundaries,
and integration recovery through claim, file-publication and manifest receipts.
The permanent opt-in NFS capability remains; production NFS and source cleanup
remain disabled. No package, REST field or schema changes are introduced.

Production gate `20261014T120045Z-c23e0a5e` and qualification gate
`20261014T120046Z-91b1f651-nfs-qualification` passed 114 tests per profile in
debug and release. All 20 artifacts per mode passed loader/library/GLIBC audits
and exact pinned SLES execution; maximum required GLIBC remained 2.18, below the
2.22 limit. The locked Linux dependency count remained 42. Formatting, Clippy,
six negative audit controls per build mode and the existing trace-matrix check
passed. Both gates finished without cleanup errors. See
[production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).

Controlled fixture run `nfs-20261014T122721Z-d9131152` passed all six actual REST
transfer cases: NFS source, NFS destination and both, in debug and release.
Each reached 202 and Committed, with stable-ID replay, immediate original-path
reuse, intact retained private sources, correct destination hashes, preserved
nested paths, an empty file, a multi-buffer file and the exact V1 manifest.
Both production profiles still refused NFS before creating SQLite. The existing
OS lock/outage and isolated-startup checks also passed, and fixture cleanup
reported no errors. See [final NFS evidence](RUST-NFS-BASELINE-EVIDENCE.json).

This is a normal-operation baseline and targeted process-crash evidence, not
full runtime outage qualification. Rust claim/copy/publication interruption on
NFS, coordinator death, competing clients, stable export authorization and server
reboot/power-loss durability remain future work. The SLES container shares the
WSL2 kernel and CPU; an actual SLES host is not part of this qualification plan.
