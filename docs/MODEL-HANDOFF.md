# Model-independent project handoff

Saved 2026-11-11 for a change of AI model. This is a repository file, not a
provider memory. It contains no passwords, keys or operational state. Read this
alongside AGENTS.md; this summary does not grant new implementation/deployment
permission or override the user's decisions.

## Start here

1. Read AGENTS.md and this file.
2. Read docs/RUST-INCREMENT-128.md and docs/ADMIN-ACCOUNT-SETUP.md for the latest
   completed increment and exact operating limits.
3. For the next dashboard work, read docs/dashboard/ADMIN-SESSION-DESIGN.md,
   docs/dashboard/BACKEND-MAP.md and the dashboard sequence in docs/ROADMAP.md.
4. Consult docs/AGENT-WORKFLOW.md for coordination and
   docs/RUST-RELEASE-CLOSURE.md for release obligations. Older dated checkpoints
   are historical; do not treat every old unfinished claim as current.

The account-setup task is complete. Update 2026-11-11: the new model continued
with increment129 (in-memory session core); see docs/RUST-INCREMENT-129.md.
The user approves deleting this file once everything here is captured elsewhere.

## Checkouts and baseline

- Canonical Windows checkout: D:\GIT\GIT-GitHub\joey-huckabee\background-file-mover
- Separate Ubuntu WSL2 test clone: /home/joey/GIT/background-file-mover-testing
- Both were clean and synchronized to main at 67f57069e8c244ca43848129bf61fdd210449ce2 before this handoff-only
  change. The handoff commit will advance main without changing Rust inputs.
- Qualified source commit: de8bcbeb4f5347e8b58b3f2bed07c186b559ca79
- Qualified Rust tree: 6c8af60822a16d778a8ed2334c37dc9fe8a3f2df
- Account source PR21 merged as c7c4633c4ea06ba1431bca183d834856a12993ee.
- Instructions/evidence PR22 merged as 67f57069e8c244ca43848129bf61fdd210449ce2.
- Use short-lived branches from current main and reviewed PRs. Do not resurrect
  the historical long-lived development branch or retired implementation/tools.
- Fetch before assuming a checkout is current. Never overwrite another agent's
  or the user's edits, force-push, or reset hard.

## What is implemented now

The Rust service already has scoped implementations/evidence for durable SQLite
custody/recovery, source/destination binding and enrollment, supervised workers,
UUID producer replay, manifest v2 with preserved legacy-v1 recovery, explicit
schema11-to12 offline migration, protected Unix ingress, native producer mTLS,
live certificate reload/revocation, bounded TLS execution and independent
curl/OpenSSL interoperability. These are bounded slices, not release approval.

Increment127 added the approved Argon2id password primitive. Exactly five packages
were added then: argon2 0.5.3, base64ct 1.8.3, blake2 0.10.6, password-hash 0.5.0
and rand_core 0.6.4. Existing versions/checksums were preserved. The fixed PHC
profile is Argon2id v19, m19456/t2/p1, 16-byte salt and 32-byte tag. Application
entropy uses the existing TLS crypto provider. Consult its evidence for limits;
do not claim complete memory erasure or a complete advisory audit.

Increment128 added these offline host-local commands:

```text
file-mover --admin-account-init CONFIG.json --account-dir EXISTING_PRIVATE_DIRECTORY [--stdin]
file-mover --admin-password-change CONFIG.json --account-dir EXISTING_PRIVATE_DIRECTORY [--stdin]
file-mover --admin-account-status CONFIG.json --account-dir EXISTING_PRIVATE_DIRECTORY
```

Important implementation facts:

- Run as the same non-root service UID/non-root primary GID. Existing supported
  schema12 state and recorded active source pairing are required. No state
  initialization, migration or payload probing occurs in these commands.
- Stop the mover and wait for surviving workers to exit first, including for
  account status. Do not remove locks/worker evidence or change state paths to
  bypass exclusion. Live password activation is future work.
- A private same-executable helper owns InstanceGuard, its own recorded worker
  process group and account.lock through actual exit. The foreground parent
  keeps its original group for no-echo TTY input. It waits for helper preflight,
  sends bounded JSON through a private pipe, and waits for actual helper exit.
- Closing input before submission aborts; after submission a helper can complete
  publication after its input-owning parent dies. Lost responses are uncertain;
  never automatically retry, restore, repair or adopt staging leftovers.
- Account directory is precreated, local, owned0700 and disjoint from state,
  current/retained payload roots and ingress/TLS credential parents.
- Fixed files: admin-account.json, persistent account.lock, admin-account.next.
  Records/lock/stage are private0600. Init is no-clobber; replacement validates
  expected old bytes/custody, syncs and atomically publishes. Uncertain outcomes
  and leftovers refuse until reviewed; no reset/repair tool is provided.
- Strict record v1: instance_id, random stable account_id, exact username,
  positive u64 revision and fixed-profile verifier. Replacement preserves
  principal/username/instance, increments revision without wrap.
- Username1-128 UTF-8 bytes; password1-4096 bytes; no trimming/normalization.
  Default input hides username/password and repeats the new password. Catchable
  aborts restore saved terminal flags and flush queued input. SIGKILL cannot.
- Explicit --stdin is nonterminal, strict bounded JSON (65536 bytes), rejects
  duplicate/unknown fields. Init requires username/password/confirm_password;
  change requires only password/confirm_password and cannot rename the account.
- Provisioned public status has exactly provisioned/version/username/revision;
  version is numeric1, revision is a decimal string. Missing account returns
  only provisioned:false. No verifier, account ID or instance ID is disclosed.
- Ordinary host devtmpfs and the observed OCI devtmpfs /tty bind are handled by
  a terminal-specific policy, opened character-device5:0 and foreground checks.
  Credential/account storage policies were not relaxed.
- No packages were added in128. Existing rustix termios/pty features and the
  already locked subtle dependency edge were selected and gated.

Primary code: file-mover/src/account.rs, account_cli.rs, password.rs;
mover-fs/src/account_file.rs, terminal.rs and the terminal policy in instance.rs.
API tests include tests/support/account_cli.rs. All paths are under rust/crates/.

## Validation: preserve these distinctions

Required PR CI run42970695084 completed successfully for the qualified source:

- Full production:344 tests in each debug/release profile.
- Full nfs-qualification build mode:348/profile. This is not real NFS qualification.
- Production job:10 formal account terminal cases, protected-ingress checks and
  140 independent HTTPS client operations.
- 12 portable account-driver tests and 5 gate-safety tests passed.
- 89 Rust input hashes/seven pins and all four CI native compiler audits were
  checked. Native audits cover397 source compilations each through the selected
  compiler/sysroot for glibc2.22. CI raw executable bytes were not uploaded for
  independent coordinator rehash.

Local pack rust/validation/20261111T061232Z-9f951dc8 is UNFINALIZED:

- Its surviving logs contain344/344 passing tests and its console printed PASSED.
- No final report.json survived a WSL restart. The runner prints PASSED before
  cleanup/report writing. Do NOT reconstruct a receipt, claim a finalized local
  full-gate pass, or use this pack as a passed input to the registered checker
  or offline-bundle producer. Historical finalization/cleanup cannot be inferred
  merely from the console line.
- Separate retained-data audit checked all89 archived Rust inputs,22 executable
  hashes/ELF/test logs and both native compiler audits. All11 release binaries
  are byte-identical to the CI-qualified release set. Debug hashes differ;
  no debug reproducibility claim is made.
- A fresh separate local retained-binary diagnostic replay passed all10 terminal
  cases and cleaned up. It is diagnostic, not a substitute for full gates.
- The registered checker correctly refused the pack without its final receipt;
  that failed probe is preserved. CI is the qualification basis.

Durable public evidence is docs/ADMIN-ACCOUNT-EVIDENCE.json. Do not substitute
ignored scratch files for its conclusions. Exact replay-driver bytes are embedded
as base64 with their original hash. They contain40 LF-only endings,1 finalCRLF
and0 CR-only endings; do not normalize and then claim the old hash.

The raw local packs and scratch scripts under rust/validation/ are ignored and
are not transferred by Git to Cloud threads. Keep successful evidence; preserve
failed/superseded attempts without counting them as passes. Independent review
closed all code/evidence findings, including the newline metadata correction.

## Product decisions that must not be reopened accidentally

- Native HTTPS in the Rust executable; no external proxy is to be introduced.
  Producer TLS-off mode is explicit loopback-only HTTP, never a TLS-error fallback.
  Admin HTTPS is a separate planned audience, not the producer mTLS identity.
- Transfers belong to the service, independent of dashboard credentials.
  Manual logout/password activation revoke all dashboard sessions, not transfers.
  Restart clears sessions; default inactivity timeout is configurable30 minutes.
  These session behaviors are approved contracts, not implemented runtime yet.
- Written v2 contract is frozen through approved groups1-53. Preserve UUID replay,
  current-startup size policy, request identity and legacy custody/v1 bytes.
- Group50 clear forgets ALL job linkage to source/destination files, ownership,
  accounting/inventories and action results while leaving files in place. No
  post-clear reconstruction/adoption. Effects must settle before eligible clear.
  Never restore the old retained-ownership-after-clear behavior.
- Dashboard: plain HTML/CSS/JavaScript, original SVG icons, local fonts; no frontend
  packages/build tools/CDNs/external assets. User approved the mockup direction
  at docs/dashboard/mockup.html, not every fictional metric/action. A UI trim and
  refinement step is explicitly retained in docs/ROADMAP.md.
- Both required pinned cargo-libc/SLES gate modes and independent review apply
  to substantive Rust increments. Build migration is cargo-libc0.2.4, glibc2.22
  and independent ELF/native audits. Retained Zig C fixtures are a separate boundary.

## What remains / authorization boundary

No real account/credential/state has been created or modified for the user.
There is no admin HTTP listener, browser login, session manager or real dashboard
connection yet. Dashboard reads/actions are not all implemented. Never infer
backend or release completeness from a polished mockup or an offline bundle.

Recommended next bounded work is the session manager, bounded verifier execution,
global revocation/admission and guarded live account activation, followed by
separate admin HTTPS/login/session routes and embedded assets, then real read
APIs/UI integration and reviewed action increments. Read the design and latest
user direction first. The current model-switch request does not authorize
starting these next runtime features automatically.

All eight FR release gates remain open. No deployment, operational conversion,
production NFS, source deletion, physical durability, FIPS or shipping approval.
Packaging/offline-bundle qualification follows backend/UI and release prerequisites.
No automatic new NFS experiment, takeover/rebind, state repair or payload adoption.

The last user question concerned administrator rights. Answer distinction:
OS administration is generally needed for initial service-account/directory
ownership provisioning, systemd unit installation/control policy, mounts/firewall
and system-wide installation. Normal runtime and host-local account commands run
as the dedicated non-root service user. Account commands explicitly refuse root.
Systemctl authority requires host-admin policy; the app's own stop/status controls
use the service identity. Future dashboard admin is an application role, not
Linux root. No policy change or privilege-elevation feature was requested.

## Agent workflow and practical tool notes

- Cloudroom project proj_yhjr5wn4cn; coordinator thread thr_grm8wj2gt7.
- Existing read-only reviewer thr_xnjapdndei; specialist thr_vve4njpt8u, both idle
  at handoff. Use room-cli, not another agent CLI or built-in harness subagents.
  Follow docs/AGENT-WORKFLOW.md: coordinator plus independent reviewer, optional
  one bounded specialist with exclusive file ownership, generally max3 agents.
- Local threads run room-cli status --json before acting. Read its skill when
  needed. Current Windows fallback launcher is Node plus
  C:/Users/Joey/AppData/Local/Programs/Cloudroom/resources/app.asar.unpacked/node_modules/bb-app/host-daemon/dist/room-cli.
  This is Cloudroom's bundled room-cli; do not invoke another product's CLI.
- Push committed inputs before Cloud delegation. Pull/rebase before pushes;
  use pull --no-rebase for unpublished merge commits. No force pushes.
- One heavy local build/test job at a time. The Cloud reviewer is ARM64 and is
  not the x86_64 SLES execution host. Do not install local tools without permission.
- WSL main tracks coordinator/main (the Windows checkout); origin is GitHub.
  Both were synchronized and clean. Refresh the coordinator remote if its
  tracking pointer is stale; do not mistake that for unpublished product work.
- WSL can start slowly after sleep/restart and emit systemd user-session warnings.
  Do not restart shared WSL globally, kill unrelated processes, enable lingering
  or change system configuration casually. The last diagnostic used runuser as
  joey with task-local XDG_RUNTIME_DIR=/run/user/1000 and inherited root DBus
  address removed. No persistent service/configuration change was made.
- Avoid nested PowerShell/WSL/bash quoting and command substitutions. Use a small
  Python script with subprocess arguments and explicit cwd for multi-step sync.
  An outer-shell expansion once ran Git in the Windows mount as Linux root and
  triggered a dubious-ownership warning; no global safe.directory exception was
  added. Normal operations as joey in the separate clone work.
- Read local WSL evidence from Windows through \\wsl.localhost\Ubuntu\home\joey\GIT\background-file-mover-testing
  when useful. Hash committed Git blobs for canonical inputs; Windows checkout
  line endings can differ. Preserve exact report/driver bytes for recorded hashes.
- Known owned test containers were verified absent/removed. Cached images,
  registry volumes and shared Podman helpers were deliberately preserved.
- Tests use disposable roots/state/credentials only. Never request or commit
  actual passwords, keys, .env contents, live SQLite state or production payloads.

## Useful links

- docs/ADMIN-ACCOUNT-SETUP.md: end-user commands, permissions and recovery.
- docs/RUST-INCREMENT-128.md: implemented scope, qualification and limitations.
- docs/ADMIN-ACCOUNT-EVIDENCE.json: exact public proof records and driver bytes.
- docs/dashboard/ADMIN-SESSION-DESIGN.md: next session/admin design boundaries.
- docs/dashboard/BACKEND-MAP.md: real fields, omissions and missing backend work.
- docs/ROADMAP.md: dashboard delivery and required later UI refinement.
- docs/RUST-RELEASE-CLOSURE.md: open FR/RC/P release obligations.
- docs/AGENT-WORKFLOW.md: team roles, synchronization and review rules.

There is no unfinished account-setup implementation to restart. If the next user
asks what is next, propose the bounded session/global-revocation integration;
explain that it precedes connecting the dashboard. Keep status claims scoped.
