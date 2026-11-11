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

Pending final qualification. Twelve portable account-driver tests and five
SLES-gate safety tests pass. Independent review findings about queued terminal
input, status revision representation and cleanup ownership have been addressed
and reviewed without additional actionable findings. Full production and
qualification modes, actual-target PTY execution and final evidence remain pending.
Superseded compile failures and interrupted runs are not qualification passes.

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
