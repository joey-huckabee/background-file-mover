# Increment 133: readable startup and command errors

Requested during the 2026-11-12 UI review after a WSL demo refused to start with
`Error: "Blocked(\"ingress mount/alias custody\")"`, which named no path, cause
or remedy. Behavior is unchanged: the same conditions refuse; only the messages
change.

## Change

- User-facing commands print `file-mover: <reason>` as text instead of Rust
  debug output. Internal worker invocations keep their previous stderr bytes,
  because some worker stderr streams are IPC channels.
- `ClaimError` displays readable text. A new `Refused(String)` variant carries
  path context for preflight refusals. Persisted job diagnostics still use fixed
  codes (`blocked: path refused`), so paths never enter stored state.
- Mount checks for account, credential and socket paths now say which path, which
  rule (path is a mount point, inside a subdirectory bind mount, or reachable via
  a second mount, naming it) and what to do, including the WSLg case.
  Non-local filesystem refusals name the filesystem type and mount.
- Startup prefixes the configuration field: `admin_ingress.account_directory`,
  `admin_ingress.server_certificates|server_ca_certificates|server_key`,
  `native_ingress.operator_socket|server_certificates|server_ca_certificates|client_ca_certificates|server_key`,
  `protected_ingress`.
- Account commands show path refusals (which happen before any account I/O)
  instead of the generic "account custody or publication refused". The private
  helper now classifies failures by error type, not message text, and sends a
  bounded (1024 characters), control-character-free explanation for path refusals
  only. A configured path containing words such as "owns state" cannot change
  the reported outcome.
- [Troubleshooting](ADMIN-HTTPS-SETUP.md#troubleshooting) lists each message and remedy.

Before/after on the same WSL config:

```
Error: "Blocked(\"ingress mount/alias custody\")"
file-mover: native_ingress.operator_socket: /home/…/operator/api.sock is on a filesystem that is also mounted at /mnt/wslg/distro. Credential, account and socket paths must be reachable through exactly one mount so their ownership checks cannot be bypassed. Move them to a filesystem mounted only once, or remove the extra mount (on WSL, WSLg mirrors / at /mnt/wslg/distro; see docs/ADMIN-HTTPS-SETUP.md#troubleshooting)
```

## Tests

- Unit: synthetic mount tables for the WSL alias, subdirectory bind mount and
  mount-point cases name the path and conflict; a single whole-filesystem mount
  passes. `ClaimError` text contains no debug quoting.
- Real service: the missing-account startup refusal reads
  `file-mover: admin_ingress.account_directory: …` with no debug quoting.

Independent review of the first revision found that path text could reach the
helper's substring classification (P2) and that account commands still hid the
explanation (P3). Both are fixed with unit tests. A follow-up P2 found the
helper's first-line reader (1024 bytes) could reject an escaped explanation; the
writer and reader now share one 4096-byte line bound, the writer shrinks the
explanation until the escaped line fits, and a test pushes a worst-case escaped
refusal through the bounded reader.

## Validation status

PR32 CI run
[43209050904](https://github.com/joey-huckabee/background-file-mover/actions/runs/43209050904)
at `51d1075` passes both full modes: production **377 tests per debug/release
profile** and nfs-qualification **381/profile** (increment132's 372/376 plus 5
unit tests). Independent review: no remaining findings. Merged to main as `d29fec0`.
