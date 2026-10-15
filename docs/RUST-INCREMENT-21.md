# Increment 21: Three-minute NFS outages and live recovery

This increment extends the retained fixture with SC-051/052: a source claim
blocked on NFS and an independent destination verification read blocked on NFS.
Each runs in debug and release, with at least 180 seconds of outage observations
after the worker is released from its local rendezvous into real filesystem work.
The 60-second qualification pause budget is unchanged; it is not used to simulate
the long outage. Production NFS and source deletion remain disabled.

The driver samples health/status and the assigned child about every 15 seconds.
It requires HTTP 200 with each health/status request under five seconds, unchanged
file and manifest phases, unchanged path-release state, exactly the same one
assigned worker and observed kernel-blocked state D. Verification additionally
requires the local read-completed marker to remain absent: a blocked metadata
operation after a cached full payload read is insufficient evidence.

Three sequential same-ID retries exercise the recorder contract. During blocked
claiming they must return retryable 503 handoff_pending or service_busy and leave paths unreleased;
the original request must also fail to acknowledge custody during the outage.
During verification the already completed claim must replay 202 for the same job.
The submission queue has one pending slot. A timed-out HTTP wait does not cancel
that queued command; subsequent retries can observe service_busy. The fixture
must allow that response while requiring no worker accumulation or premature
acknowledgement. This is not a concurrent queue-flood or memory-capacity test.

After restoring NFSD, the same coordinator must finish without restart or signals,
commit attempt 1, preserve the private source and any reused producer path, and
produce the exact expected manifest and independently checked source/destination
hashes. The completion manifest is absent before the outage; unchanged durable
phases and the blocked worker establish no recorded commitment during the outage.
The driver does not issue destination NFS probes while NFSD is unavailable.

Production gate `20261015T012700Z-dd52806f` passed 115 tests per profile;
qualification gate `20261015T012712Z-556e5ee0-nfs-qualification` passed 116.
Both passed formatting/Clippy, debug/release zigbuild, loader/library/ELF audits,
six negative audit controls per mode and exact target execution in pinned SLES
userspace. Maximum required GLIBC remains 2.18; the external Linux graph remains
42 locked packages. Both gates finished successfully without cleanup errors.
See [production evidence](RUST-SLES-EVIDENCE.json) and
[qualification evidence](RUST-SLES-QUALIFICATION-EVIDENCE.json).
The gates use Windows `CONTAINER_CONNECTION=podman-machine-default-root`, with
native Linux container builds and pinned userspace execution as documented in
[NFS qualification](NFS-QUALIFICATION.md). No permanent engine or Ubuntu
configuration changes are made.

No Rust source, dependency, schema, API, pause
budget or production execution behavior changes are required by these tests.

The initial fixture `nfs-20261015T013433Z-42fc54d6` passed six baselines,
all eighteen existing runtime/control cases and both longer verification cases.
Both longer claim cases failed the driver's overly strict `handoff_pending`
assertion: their second retry returned 503 `service_busy`, retryable with paths
unreleased. Its overall result is FAILED, not a qualification pass; cleanup had
no errors. Inspection confirmed the existing submission channel has one pending
slot and an HTTP timeout leaves the queued command intact. The driver now accepts
both temporary responses, requires observed backpressure and exactly three
retries, and checks that worker count stays one. No service change was necessary.

The follow-up uses `--runtime --long-outages-only`: it repeats all six normal
baselines and the OS/startup checks, but runs only the four longer runtime cases.
Earlier interruption evidence is preserved in
[the existing runtime report](RUST-NFS-RUNTIME-EVIDENCE.json); the new passing
outage report is kept separately rather than replacing that report with a
restricted-scope run. Per-case result files are now written after cleanup so
failure details are available while subsequent cases are still running.

Follow-up fixture `nfs-20261015T020953Z-dfbd3a1b` PASSED with no cleanup errors:
all six normal NFS baselines, all four selected runtime cases and the retained
OS/inherited-lock/startup-shutdown probes passed. See the complete
[long-outage evidence](RUST-NFS-LONG-OUTAGE-EVIDENCE.json), explicitly labeled
`runtime_scope: long-outages-only`. It does not claim to rerun the eighteen
short interruption/control cases in this follow-up. Those passed in the initial
run and their earlier full passing evidence is retained separately.

| Profile / situation | Outage observation seconds | Recovery after restore seconds |
|---|---:|---:|
| Debug claim | 193.422 | 17.515 |
| Debug verification | 194.984 | 17.359 |
| Release claim | 193.375 | 17.422 |
| Release verification | 194.844 | 17.360 |

Each case observed the same worker in D at every sample, the same live
coordinator PID, unchanged file/manifest phases and three same-ID retries.
Both claim cases observed 503 handoff_pending followed by two 503 service_busy
responses; all left paths unreleased. All six verification retries returned
202 for job 1. Both original claim requests returned 503 during unavailability.
After restoration all four committed attempt 1 without restarting, with expected
source/destination hashes and exact V1 manifest contents. Root observations stayed
stable, private sources remained retained and reused producer paths stayed intact.
Maximum sampled health/status round trips were 1.750/1.735 seconds including
host/container command overhead, below the fixture's five-second bound; these
are not production performance guarantees.

The container used kernel `6.18.33.2-microsoft-standard-WSL2`. Final inventory
confirmed no fixture containers, networks or export volumes remained. Only the
default Podman network and intentional Rust toolchain/registry caches remained.
NFS modules and the saved fixture image are retained for future qualification.
Python syntax/CLI validation, scenario IDs/document links, whitespace and the
historical trace-matrix checks also pass. SC-051/052 are now Fixture; DOC-01–06
remain the maintained user-guide backlog. No formal Rust requirement trace
coverage is promoted by these scenario keys.

Scope remains one controlled NFSv4.1 hard-mounted client and an NFSD service stop
on a modern WSL2 kernel, with pinned SLES/glibc 2.22 userspace. The server container,
export and client mount remain intact. Arbitrary/indefinite outages, queue floods,
server reboot, export replacement, power loss, old kernels/CPUs and cross-client
fencing remain unqualified. Recovery and cleanup always restore NFSD before
waiting for filesystem users and unmounting/removing only fixture resources.
