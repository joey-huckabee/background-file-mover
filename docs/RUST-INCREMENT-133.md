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
  instead of the generic "account custody or publication refused".
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

## Validation status

Pending PR CI for both full SLES modes and independent review.
