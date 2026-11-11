# Guarded local account setup: implementation slice

The user requests account setup after increment127. Implement offline-only
`--admin-account-init`, `--admin-password-change` and nonsecret
`--admin-account-status`, with CONFIG.json and explicit `--account-dir DIR`.
No remote account route, admin listener, login or session activation. Running
daemons/surviving workers refuse under InstanceGuard; live replacement IPC and
session revocation belong to the subsequent integration and must precede any
claim that changing an active password is supported.

Use existing supported schema12 state and recorded active source pairing,
without source/destination filesystem access, initialization or migration.
An owned private helper holds the guard/worker epoch through SQLite closure and
all account/hash I/O. It signals readiness only after state/account preflight.
The foreground parent handles no-echo input without changing its process group,
then sends bounded JSON through the private pipe and waits for actual helper exit.
Closing input aborts an unsubmitted helper; a submitted publication may finish
after parent death, retaining exclusion until actual helper exit.
Account directory is precreated, local, service-owned0700, outside state and all
current/retained payload and ingress/credential scopes. Fixed account filename
`admin-account.json`; no arbitrary leaf or automatic directory creation.

Record strict bounded version1 JSON: existing instance_id, stable OS-random
32-byte lowercase-hex account_id, exact username, positive u64 revision, fixed
Argon2id PHC verifier. Init is no-clobber; password change preserves account_id
and username, increments revision without wrap. No plaintext/session/job data.
Status returns only provisioned/version/username/revision and no verifier.

Input defaults to a no-echo local TTY with repeated new-password entry. Explicit
`--stdin` accepts one bounded strict JSON object for automation, with duplicate/
unknown-key rejection and exact UTF-8 validation; no argv/env password options.
Prompts/diagnostics never echo secret input. Abort/catchable signals restore TTY
settings. SIGKILL cannot be handled; document terminal recovery. No new package;
the existing rustix termios and test PTY capabilities are selected and audited
on SLES.

Storage API (specialist-owned new `mover-fs/src/account_file.rs`):

```text
pub struct AccountDirectory { private ... } // owns a separate account.lock flock
pub fn open(directory: &str, excluded: &[String]) -> Result<AccountDirectory>
impl AccountDirectory {
  pub fn read(&self) -> Result<Option<Vec<u8>>>;
  pub fn publish(&self, bytes: &[u8], expected: Option<&[u8]>) -> Result<()>;
}
```

`Result` is existing mover-fs ClaimError. Bound contents to8192 bytes. `expected`
None means require absence; Some means exact old bytes/custody still match before
replacement. Reject leftovers, unsafe parent/file/lock, symlink/hardlink/mount,
nonlocal/foreign state and every error except true NOENT as absence. Check full
fixed names before named I/O. Use `credentials` directory/read checks; coordinator
exposes `parent_directory`, `parts`, `local`, `check_file`, `unchanged` as pub(super).
Separate fixed0600 single-link `account.lock` protects shared directory use across
state paths; never unlink/replace its inode. Hold it through publication/closure.

Write exclusive0600 `admin-account.next`, sync file, validate directory/name
identities and expected old file. Init uses no-clobber publication compatible with
the existing Linux/SLES boundary (link/unlink if appropriate); replacement uses
atomic rename. Sync parent and verify final single-link0600 file and bytes.
Before publication, only clean an exact owned staging inode; never unknown
leftovers. Once publication may have happened, any error is OutcomeUncertain;
never automatically restore/retry/adopt. Explicit stale staging files refuse.
Fault hooks, if used, are test-only. Exact tests cover no-clobber, stale expected,
cross-open exclusion, unsafe paths/links/modes, prepublication and late-sync
failures. CLI tests additionally prove live guard/orphan refusal, existing-state
only behavior, metadata/payload preservation, secret-free results and restart
load of the new verifier. Both full SLES modes and independent review required.
All credentials/state are disposable fixtures; no deployment/NFS/deletion/release.
