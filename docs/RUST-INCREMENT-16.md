# Increment 16: Retained NFS qualification build and baseline

The user requested retaining the qualification capability permanently. Its build
feature, labels, equivalent SLES gates, fixture procedure and future packaging
rules are explained in [NFS-QUALIFICATION.md](NFS-QUALIFICATION.md).

The default build continues to reject NFS. An explicit compile-time feature
admits NFS roots solely for controlled qualification, while all transfer and
custody code remains shared. No package, schema, REST endpoint or cleanup policy
is added. Internal worker modes remain part of the same executable. CI validates
production and qualification modes separately; fixture work stays local and
container-only.

The normal-operation runner exercises the actual REST coordinator and filesystem
workers for NFS source, destination and both directions in both profiles. It
uses local SQLite, omitted sizes, nested paths, multi-buffer payloads and empty
files. It checks 202/replay, path reuse, retained source bytes, destination bytes,
hashes and V1 commitment. It records failed cases rather than treating fail-closed
responses as successful transfer qualification.

Production run `20261014T102804Z-c60dca93` and qualification run
`20261014T102818Z-a9f7fb37-nfs-qualification` passed all 105 tests per profile.
Both debug/release variants passed ELF/library/loader audits and exact execution
in pinned SLES/glibc 2.22 userspace, with maximum required GLIBC_2.18, 42 external
Linux packages and no cleanup errors. Each mode emitted 20 audited artifacts;
there is still one deployed service executable. Formatting, Clippy, six negative
audit controls and the existing trace-matrix check passed.

The controlled normal-operation baseline did **not** pass. Both profiles showed:

- NFS source, including the both-NFS case: 409 `recording_blocked`, no source-path
  release and original contents intact. Status remained `Accepted/AwaitingClaims`
  with all files pending; the available status does not identify the precise
  failing observation/allocation/effect call.
- Local source/NFS destination: 202 and replay succeeded, original paths could be
  reused, and all private source hashes remained correct. The first destination
  file reached `Verified/PublishIntent`, then three failures required review.
  No completion manifest appeared. The remaining files were retained and were
  not delivered; multi-buffer/empty-file destination execution remains unproven.

Opaque worker errors do not prove which syscall caused these refusals. Next add
bounded phase/operation/errno evidence as needed, then resolve the refusal with
explicit recovery rules. Do not assume a generic link/unlink fallback is safe
or attribute every refusal to NOREPLACE without evidence. The runner records
failure and stops before outage testing; it never promotes blocked transfers to
successful qualification. Final run `nfs-20261014T110057Z-4ae7639d` records this
failed baseline (superseded by [increment 17](RUST-INCREMENT-17.md)),
with no cleanup errors. It additionally verified the first NFS destination staging
file's hash after publication was blocked. Both production profiles rejected NFS
before creating SQLite. Earlier baseline run `nfs-20261014T105226Z-71cdf499`
showed the same failure boundaries; the final runner reads the nested status
condition correctly and captures staging integrity evidence. The standard SLES
passes are recorded separately in [RUST-SLES-EVIDENCE.json](RUST-SLES-EVIDENCE.json)
and [RUST-SLES-QUALIFICATION-EVIDENCE.json](RUST-SLES-QUALIFICATION-EVIDENCE.json).

NFS interruption, coordinator death, competing clients and export authorization
remain future work; production NFS and source deletion remain disabled.
