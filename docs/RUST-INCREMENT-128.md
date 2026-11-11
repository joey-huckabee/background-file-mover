# Increment 128: guarded offline account setup

The user authorizes account setup after the qualified password primitive in
[increment127](RUST-INCREMENT-127.md). This slice implements host-local account
initialization, password replacement and nonsecret status. It does not activate
an admin listener, login, sessions or the dashboard's service connection.

## Implemented boundary

- Use only existing supported schema12 state with recorded active source pairing.
  Inspect retained roots from local state; never bootstrap or inspect payloads.
- A private same-executable helper owns InstanceGuard, the recorded worker epoch
  and separate persistent account.lock through actual exit. The foreground parent
  keeps its original process group for no-echo input. It accepts input only after
  helper preflight, sends bounded JSON through its private pipe and waits for exit.
- A killed input owner cannot release a surviving helper's exclusion. Before
  submission EOF aborts; after submission hashing/publication can finish without
  the parent. Lost results are uncertain, never automatic cancellation or rollback.
- Require a precreated local service-owned0700 account directory outside state,
  current/retained payloads and ingress/TLS credential parents. Fixed names,
  pre-stat mount exclusions, no symlinks/hardlinks, bounded reads and stable
  descriptor/name checks preserve the existing cooperative local custody model.
- Store a strict version1 instance-bound record, random stable account principal,
  exact username, positive u64 revision and fixed-profile Argon2id verifier.
  Init is no-clobber; replacement preserves identity and advances revision without
  wrap. Stage/file/parent synchronization and final validation precede success.
  Uncertain publication or leftover staging requires inspection, never adoption,
  automatic restore or retry. No reset/repair command is added.
- Default foreground TTY input hides username and both password entries, bounds
  bytes and time, handles catchable signals, flushes unread input and restores
  saved terminal settings. SIGKILL/host crashes cannot run restoration.
  Ordinary host devtmpfs and the observed OCI devtmpfs `/tty` bind are supported
  only after pre-open mount checks and opened character-device5:0/foreground-group
  validation. Remote/wrong leaves and effective aliases refuse. Account/credential
  storage mount policies are unchanged.
- Explicit nonterminal --stdin uses strict bounded UTF-8 JSON, rejecting duplicate
  and unknown fields. No password argv/environment option. Secret-owning buffers
  are zeroizing; this is not proof of erasure of every allocator/kernel copy.
- Provisioned public status has exactly provisioned/version/username/revision;
  revision is a decimal string. Missing accounts return only provisioned:false.
  Account IDs, instance IDs and verifiers never enter public status.
- No packages are added. Existing rustix termios/PTY features and an already
  locked subtle dependency edge are selected and checked by the existing gate.

[User setup and recovery instructions](ADMIN-ACCOUNT-SETUP.md) document the exact
commands, offline service requirement, automation, terminal repair and uncertainty.
[Implementation scope](ADMIN-ACCOUNT-INCREMENT.md) records the lower-level contract.

## Validation status

PR21 CI run [42970695084](https://github.com/joey-huckabee/background-file-mover/actions/runs/42970695084)
passes both full modes: production **344 tests per debug/release profile** and
qualification **348/profile**. Its production job also passes all **10 account
PTY cases**, protected ingress and **140 independent HTTPS client operations**.
Downloaded production/qualification reports and all four native compiler audits
were checked. All 89 production Rust input hashes match the committed source;
the synthetic CI checkout has the same Rust tree. CI executable bytes were not
uploaded for an independent coordinator rehash.

Twelve portable account-driver tests and five SLES-gate safety tests pass.
Independent review findings about queued input, revision representation, cleanup
ownership and host/container terminal mounts have been addressed and reviewed.
The retained local test logs contain **344 passes in each profile**, and the
console printed PASSED. No final `report.json` survived the WSL restart. The
runner prints that console line before cleanup/report finalization, so the local
pack is explicitly **unfinalized**; no reconstructed local gate pass is claimed.
Qualification comes from the completed CI gates above. Independent review found
no scope conflict with that evidence boundary.

The coordinator independently compared all **89 archived Rust inputs**, rehashed
all **22 retained executables**, rechecked their ELF/test logs and reproduced both
native compiler audits. All **11 release executables** are byte-identical to the
CI-qualified release set. Debug hashes differ; no debug reproducibility claim is
made. A fresh, separately labeled retained-binary diagnostic replay passes all
**10 terminal cases** with cleanup. It does not replace the registered checker's
full-gate prerequisite. The registered checker correctly refused the unfinalized
local pack; its refusal is preserved rather than overwritten.

[Machine-readable evidence](ADMIN-ACCOUNT-EVIDENCE.json) binds exact CI reports,
source/pins, native audits, retained artifacts and diagnostic results. The replay
driver's exact bytes/base64, encoding and hash are retained. Superseded compile
failures, interrupted runs and the earlier failed fixture check are not counted
as qualification passes. No raw terminal capture, password, PHC verifier or private
equality token is included in the public evidence.

## Reproduce on the validation host

These are build/test-host commands, not additional account-setup dependencies
for the installed service host. Use the existing pinned cargo-libc/SLES workflow
and disposable state; never operational credentials or roots.

```sh
python3 -m unittest discover -s scripts -p test_admin_account.py
python3 scripts/check-rust-sles.py
python3 scripts/check-rust-sles.py --qualification
python3 scripts/check-admin-account.py --production-gate rust/validation/FULL_PRODUCTION_RUN --report rust/validation/NEW_ACCOUNT_REPORT.json
```

The account checker requires a passed full production gate matching committed
Rust inputs and actual executable/ELF hashes. Its report must be new. Require the
final passed gate report and clean cleanup: a console PASSED line precedes those
finalization steps and is insufficient by itself. It creates
fresh private container fixtures with UID1000:GID1001, network disabled, zero
capabilities and no-new-privileges. It checks hidden input, exact terminal-flag
restoration, unchanged credentials on mismatch/interruption and revision advance
on successful change. Raw terminal/CLI captures, passwords, verifier bytes and
private equality tokens are discarded rather than published. Initialization and
password change use the installed executable with a controlling terminal or
explicit private stdin; status is noninteractive and takes no password input.
These commands do not require Python, Perl or a Rust toolchain.

## Limits and next boundary

These are offline commands. Even account status requires the mover and surviving
workers to have exited; no lock bypass or live password replacement is provided.
No admin sessions exist yet to revoke. Bounded session state, global revocation
admission and live activation remain the next integration slice, before the
separate native admin HTTPS listener and browser connection.

No real account/credential/state operation, target package installation,
deployment, production NFS/deletion, systemd/physical durability, bundle/shipping
or full release is qualified. All eight FR gates remain open. The dashboard
continues to use plain offline HTML/CSS/JavaScript and original SVG icons.
