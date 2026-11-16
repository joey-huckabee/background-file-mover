# Increment 159: live admin password activation

User request 2026-11-15: "do live password activation next" (roadmap: live
password activation over IPC). Implements the approved
[design](dashboard/PASSWORD-ACTIVATION-DESIGN.md). Before this, a password
change needed a stopped service.

## Behavior

- `--admin-password-change` while the service runs with `admin_ingress`: the
  command checks the service's account status, prompts as before (or reads
  `--stdin`), derives the Argon2id verifier itself and sends only the verifier
  with a fresh 32-byte change ID over `account.sock`. The password never leaves
  the command.
- The service (thread `mover-account`, one request at a time) checks instance,
  base revision and the exact verifier profile, re-reads the saved record
  under `account.lock` and requires it to equal the active one, publishes
  revision + 1, then activates it: under the session lock it installs the
  record and revokes every session and CSRF token, then waits up to 10 s for
  dashboard actions admitted earlier (`settled`).
- Replies: `activated` (`revision`, `settled`, plus `change_id` from the
  command), `unchanged` (`code`) or `uncertain` (`code`). Nonzero exit for
  anything but `activated`. A lost reply asks status for the change ID once.
- `--admin-account-status` while running returns `instance_id`, `username`,
  `active_revision`, `published_revision` and, with `--change-id`, that
  change's outcome and standing (`active`, `superseded`, `unverified`). The
  last 16 changes are kept in memory.
- Offline flows are unchanged. Without `admin_ingress` there is no socket.

## Transport bounds

`account.sock` is created like `control.sock` (custody checks, mode 0600) and
also checks the peer uid (`SO_PEERCRED`) equals the service's. Requests are at
most 2048 bytes within an absolute 1 s deadline, replies at most 1024 bytes
with a 1 s write bound; unknown keys, oversize or trickled frames close the
connection with no effect. The thread is joined before the instance guard is
released on every stop path.

`instance_id` is the service process identity (`pid:start`, as in
`--status`): a request prepared against one service process is refused by
another (`instance_changed`).

## Tests

- Unit (`session`): serialized activation revokes at once while an admitted
  action runs, reports `settled:false` within a short bound and `true` once the
  action ends; a stale base is refused; a login ticket taken before activation
  cannot mint a session after it.
- Unit (`account_ipc`): standing rules, change-ID format, trickled request cut
  off at the 1 s deadline, oversize refused. (The real-service test shows the
  thread serving requests after refused frames.)
- Real service over HTTPS (`live_password_change_activates_without_restart`):
  no socket without the dashboard; socket mode 0600; live change through the
  CLI: old session 401, old password 401, new password signs in, saved record
  revision 2, status by change ID `active`; socket refusals
  (`revision_conflict`, `duplicate_change`, `instance_changed`,
  `invalid_verifier`, oversize, unknown key) change nothing; a later change
  makes the first `superseded`; restart loads the latest record, history is
  empty, the old request is refused by instance and, re-aimed, by base
  revision; no password or verifier in the log.
- All 13 admin TLS tests (local WSL; 11 of 12 full runs passed; the one
  failure was not captured by name, and the new test passed 6 of 6 alone),
  account CLI API tests, file-mover unit tests, clippy and rustfmt.

## Not covered

- Publication fault injection (post-rename / post-sync failure giving
  `uncertain`, and the `unverified` standing from an unreadable or diverging
  saved record) is covered by the standing unit test only; the real-service
  fault path is not exercised.
- The settle bound with a real blocked dashboard action is covered by the
  unit test, not over HTTPS.
