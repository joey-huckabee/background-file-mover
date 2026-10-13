# Integration qualification design notes

Use these checks and findings when designing Rust deployment qualification.
The source is integration-lab at
`3e9226b09e737522e8ea404108ee6cf0e5d64c91`, retained under
`archive/integration-lab`. The archive includes the C7 dashboard history.
No provisioning or C++ deployment code is copied into the Rust implementation.
[BRANCH-REVIEW.md](BRANCH-REVIEW.md) records its commits and path inventory.

## Retain the boundaries and test intent

Keep environment creation separate from configuration and assertions. The lab's
Windows/Hyper-V provider creates a guest; SSH/Ansible configuration and service
checks target a supplied host without knowing its provider. Its layer-separation
gate is useful even if container runners replace that provider.

Separate tool installation, deployment and assertions. Tests should report
specific failures and preserve evidence instead of rebuilding a failed environment
to diagnose it. Preserve validated configuration rendering, service-user ownership,
installed binary/unit paths and permission checks.

Retain lifecycle scenarios: systemd-observed readiness, health/operator endpoints,
service identity, NoNewPrivileges, strict system protection, private temporary/home
settings, empty capabilities, and invalid configuration rejected by ExecStartPre.
Adapt exact settings to the target systemd version and record unsupported or
unenforced controls. Do not treat a unit file's contents as proof of enforcement.

## Correct the gaps before relying on a green result

**Runner exit status:** `integration/tests/run-all.sh` uses
`if ansible ... | sed ...; then`. Its POSIX shell checks the final pipeline
command's status, so successful output formatting can hide an Ansible failure.
Preserve and check the actual runner status independently of formatting; test
the harness with a deliberately failing assertion before using it as a gate.

**Confinement:** historical notes report an enforcing Rocky guest but an
unconfined_service_t process and generic bin_t binary. Empty AVC output is not
evidence of a dedicated service domain. Prove the intended domain/profile and
transition, required file contexts, permitted operations and a controlled denied
operation. Distinguish enforcement disabled/unavailable from a passing check.

**Transfer behavior:** the branch has only `01-service-lifecycle.sh`. It lacks
actual file-movement tests under confinement. An idle stop's short elapsed time
does not prove active-worker draining or correct process exit. Check active
claims/copy/verification/publication/cleanup, durable state after stop/restart,
worker failures and the actual termination result.

**Status evidence:** the README says layer 2 has not run while the newer resume
note/changelog report an end-to-end Rocky 9.8 run. Those are historical records,
not current qualification. Old VM addresses, running-state notes, tool versions
and WSL troubleshooting settings must be rediscovered before reuse.

**Network exposure:** the old lab binds the unauthenticated API to 0.0.0.0 for
remote checks. That lab-only setting must not become a production default. Keep
loopback unless an explicit authenticated/authorized deployment boundary exists.

## Provisioning and diagnostic lessons

- Pin media inputs and verify both checksums and signatures against an independently
  established key. Matching a downloaded checksum alone does not establish provenance.
- Validate rendered kickstart/ISO contents, placeholders, encoding and line endings,
  not just that an output file exists. Retain IMAPI2FS writing fixes if reusing Hyper-V.
- Keep credentials, console passwords, inventories, ISOs and VM disks outside Git.
  Reuse credentials deliberately and keep network password authentication disabled.
- Diagnose stale SSH host keys, changed addresses and attached/open ISOs explicitly.
  Branch retirement must not imply VM/disk/network teardown.
- Use unique private scratch directories. Verify command status and current diagnostics
  rather than accepting output from stale or unwritable temporary files.
- Inspect actual platform state when cached facts disagree. Ansible distribution
  mappings and SELinux facts can be misleading or missing their support packages.
- Provide rsync on both ends when using synchronize. Do not require an rc key that
  Ansible's make module omits on success; use the documented result contract.
- Bootstrap should fail if required validators are missing. Diagnose a newly created
  user-bin directory missing from PATH without reporting a false successful install.

## Rust qualification direction

Use pinned SLES 12 SP5-equivalent and RHEL 9 userspace containers, including a
compatible systemd-enabled variant where lifecycle checks require it. Keep the
user's container-first preference; this archive does not introduce an actual-SLES
host prerequisite. Container kernel/CPU, MAC enforcement, mount behavior and
power-loss coverage must remain explicit limits, not inferred guarantees.

Reuse the [NFS fixture](NFS-TEST-FIXTURE.md) for controlled mount and failure
scenarios. Add disappearance/identity checks, collisions, interrupted operations,
blocked-worker bounds and recovery evidence for the redesigned transfer protocol.
Qualify any durability claim against the exercised server/storage behavior.

Install the same inspected GNU/glibc-target Rust artifact that passed package
qualification. Replace C++ compiler/build-on-target assumptions with artifact
provenance, target-library checks, local SQLite ownership and Rust lifecycle tests.
Keep test collection fail-closed, including missing tests and skipped enforcement.
Only decide mandatory integration CI gates after the harness can reliably detect
intentional failures and accurately distinguishes tested from untested guarantees.
