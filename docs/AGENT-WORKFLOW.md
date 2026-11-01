# Local coordinator and cloud sub-agent

Established 2026-11-01 in Cloudroom project `proj_yhjr5wn4cn`.

- Local coordinator: thread `thr_grm8wj2gt7`, Codex, with canonical checkout
  `D:\GIT\GIT-GitHub\joey-huckabee\background-file-mover`.
- Cloud child: thread `thr_xnjapdndei`, Codex `gpt-6.1-sol`, linked to the
  coordinator. Delegate bounded reviews, implementation or portable Linux work;
  require changed files/commits, actual validation and blockers in its report.
- Development branch: `feature/rust-transfer-coordinator`.
- Linux test clone: Ubuntu WSL2 at
  `/home/joey/GIT/background-file-mover-testing`. The older
  `/home/joey/GIT/background-file-mover` checkout is preserved separately.

The coordinator owns integration and local validation. Cloud work starts from
pushed GitHub commits; uncommitted Windows changes do not arrive there. Commit
and push delegated inputs first, using `git pull --rebase` before every push.
Cloud work returns on its own branch; review and integrate explicitly without
overwriting concurrent local work. Resume the existing child with `room-cli
thread tell thr_xnjapdndei` and a concrete task. When the bundled PowerShell
launcher returns no output, invoke its adjacent `room-cli` script through Node.

## Synchronizing Linux tests

The WSL test clone has `coordinator` pointing to the D: checkout via
`/mnt/d/GIT/GIT-GitHub/joey-huckabee/background-file-mover`, and `origin` pointing
to GitHub. It tests committed coordinator changes. Before each run, verify the
test clone has no local edits, then run inside Ubuntu:

```sh
cd /home/joey/GIT/background-file-mover-testing
git status --short
git fetch coordinator
git merge --ff-only coordinator/feature/rust-transfer-coordinator
git rev-parse HEAD
python3 scripts/check-rust-sles.py
python3 scripts/check-rust-sles.py --qualification
```

Stop and inspect if local edits exist or fast-forward fails. Do not reset the
clone or discard evidence to force synchronization. Keep compilation and test
artifacts on Linux-native storage. Gate results live under ignored
`rust/validation/` in the test clone; preserve raw packs separately as needed.

## Verified setup and remaining limits

Initial setup readiness: x86_64 Ubuntu 24.04 on WSL2, Python 3.12.3, native rootless
Podman 5.8.2 responding to `podman info`, and both digest-pinned builder/runtime
images present. The gate's help command runs. No Rust build/test or SLES gate
was run for this agent setup; cached images alone do not establish a gate pass.
For the subsequent Cargo-libc builder change and fresh gate results, see
[the migration record](CARGO-LIBC-MIGRATION.md).

Cloud readiness: Debian 12 on ARM64, Python 3.11.2, Git 2.56.0; Podman/Docker
absent and x86_64 execution unavailable/unverified. Required SLES gates are
blocked there. Local production and retained qualification gates remain required
for Rust changes. NFS/systemd labs require their separately documented selected
prerequisites; readiness does not qualify those labs.

Read `REST-CONTRACT-HANDOFF.md` and `WORKSTATION-HANDOFF.md` before development.
Groups 1-44 are approved; retry response counts remain unapproved. All eight
release gates remain open. Agent setup authorizes no REST implementation,
production NFS/source deletion, or movement of operational state/custody.
