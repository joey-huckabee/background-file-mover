# Offline admin account setup

This guide describes the guarded local account commands and the
[account implementation slice](ADMIN-ACCOUNT-INCREMENT.md). See
[increment128](RUST-INCREMENT-128.md) for the bounded SLES checks, review and
qualification limits. These instructions do not authorize deployment or changes
to operational state. Creating this record does not by itself enable dashboard
access; browser sign-in also needs the separate admin listener described in
[admin HTTPS setup](ADMIN-HTTPS-SETUP.md).

## Prepare the existing instance and account directory

Run the installed executable as the mover's same non-root service UID and
non-root primary GID, using its original local configuration and state. The
state must already be the supported current schema (13; run `--migrate-state` first if the service reports MigrationRequired) with a recorded active source pairing.
These commands refuse missing, uninitialized, incompatible or foreign state;
they do not initialize a source, create replacement state or migrate a database.
They inspect local state without traversing source/destination payload storage.

Stop the mover through its normal local controller and wait for actual coordinator
and surviving-worker exit before any account command, including account status:

```sh
/path/to/file-mover --stop /etc/file-mover/config.json
/path/to/file-mover --status /etc/file-mover/config.json
```

Follow the [bounded-stop guidance](RUST-OPERATOR-GUIDE.md#local-service-status-and-bounded-stop).
`ShutdownIncomplete` or `OwnerUnavailable` retains exclusion; an empty child list
alone is not exit evidence. Keep the original configuration, state and custody.
Do not bypass refusal with a different database path or by removing locks or
worker evidence. These account commands do not change a running service's password.

Have the host administrator precreate a dedicated account directory on approved
local storage. `/var/lib/file-mover-account` below is an example, not an installer
default. Check its placement against the actual configuration and retained state:

- The directory must have exact mode0700 and the service account's UID and
  primary GID. The command never creates it automatically.
- Use a canonical absolute UTF-8 path, without symlinks, `.`/`..`, repeated or
  trailing separators. Ancestors must be safely owned by root or the service
  UID and non-writable by other accounts; the guarded root-owned sticky temporary
  ancestor exception is for disposable fixtures.
- Keep the directory disjoint from the state directory, every current or retained
  source/destination payload scope, producer/operator ingress parents and native
  TLS credential parents. An ancestor containing one of those scopes also
  overlaps and refuses. Use a separate sibling directory.
- The credential loader's local filesystem allowlist applies: ext-family, tmpfs
  and overlayfs. NFS, unsafe mount aliases, bind mounts and individually mounted
  account/lock/staging leaves refuse. This is cooperative local custody, not
  protection against hostile mutation by root or the same UID.

As the host administrator, replace `SERVICE_USER` and `SERVICE_GROUP` with the
existing mover identity before creating the directory:

```sh
install -d -o SERVICE_USER -g SERVICE_GROUP -m 0700 /var/lib/file-mover-account
```

Run the account commands as that service identity, with a private file-creation
mask such as `umask 077`. The command itself refuses root or a root primary group.

Select this same directory explicitly on every command. It is not recorded by
rewriting CONFIG.json. Initial account setup needs no precreated account files.

## Initialize once

Use a foreground local terminal with a controlling TTY:

```sh
/path/to/file-mover --admin-account-init /etc/file-mover/config.json --account-dir /var/lib/file-mover-account
```

After state/account preflight, the exact prompts are:

```text
Username (input hidden):
New password:
Repeat new password:
```

The username and both password entries are hidden; each prompt ends with a
space. Enter the same new password twice. Username length is 1–128 UTF-8 bytes;
password length is 1–4096 UTF-8 bytes. Values are not trimmed, normalized or
case-folded. A mismatch or invalid input refuses before submission. The complete
prompt sequence has a five-minute timeout. This command requires account absence;
it never overwrites an existing account.

Successful init prints only public status, for example:

```json
{"provisioned":true,"version":1,"username":"admin","revision":"1"}
```

The example username is illustrative. Record the chosen username through your
normal account-management procedure; do not record the password in logs or support
attachments. A successful command exits 0. A refusal or uncertainty exits nonzero;
an unsuccessful exit after submission is not proof that publication did not occur.

## Change the password and inspect status

With the service stopped and its original state available:

```sh
/path/to/file-mover --admin-password-change /etc/file-mover/config.json --account-dir /var/lib/file-mover-account
```

The exact prompts are `New password: ` and `Repeat new password: `. This is a
host-authorized offline operation; it does not prompt for the old password.
It requires an existing valid account for this instance. It preserves username,
account identity and instance linkage, and advances revision by one. Revision
exhaustion refuses rather than wrapping. Successful output has the same public
fields as init, with `"revision":"2"` after the first change.

Inspect the account without password input:

```sh
/path/to/file-mover --admin-account-status /etc/file-mover/config.json --account-dir /var/lib/file-mover-account
```

For an absent account the complete result is `{"provisioned":false}`. Otherwise
it returns exactly `provisioned`, `version`, `username` and `revision`. `version`
is the number 1; `revision` is a **decimal string**, not a JSON number. Status
never includes the account ID, instance ID, password or Argon2id verifier.
An unsafe/foreign record is an error, not an unprovisioned result. Even status
uses instance/account exclusion and can create the persistent `account.lock`;
it is not an unrestricted read of a file while the mover is running.

## Explicit stdin automation

Init and password change accept `--stdin` after the normal arguments:

```sh
/path/to/file-mover --admin-account-init /etc/file-mover/config.json --account-dir /var/lib/file-mover-account --stdin
/path/to/file-mover --admin-password-change /etc/file-mover/config.json --account-dir /var/lib/file-mover-account --stdin
```

These command lines show the consumer only. An approved secret-input producer
must supply its stdin through a private pipe, then close the pipe. A terminal
stdin is refused with `--stdin`; use the hidden prompts for manual entry.
Status does not accept `--stdin`.

Supply one strict UTF-8 JSON object, at most 65,536 bytes including whitespace:

| Command | Required string fields |
|---|---|
| Init | `username`, `password`, `confirm_password` |
| Change | `password`, `confirm_password` |

There are no optional input fields. Duplicate, unknown, missing or wrongly typed
fields, invalid UTF-8, trailing non-whitespace input and mismatched confirmation
refuse. In particular, change rejects `username`; it cannot rename the account.
The same username/password byte limits apply as at the terminal. Input is read
to EOF; an automation producer must finish and close its write end.

Keep secret values out of argv, environment variables, literal shell commands,
history, here-documents, tracing (`set -x`), pipeline logging and saved request
bodies. Use a trusted producer that obtains the secret through an approved
protected channel and writes JSON directly into the private pipe. Do not paste
password-bearing JSON into a shell or use `echo`/`printf` with a literal password.
Restrict access to the automation process and its pipes, and retain only the
public result. Do not export the account record or verifier as diagnostics.

## Storage, interruption and uncertain outcomes

The directory uses three fixed names; none is a configurable record filename:

| Name | Role |
|---|---|
| `admin-account.json` | Service-owned mode0600 record, at most 8192 bytes. It contains a version1 instance-bound account identity, username, positive u64 revision and fixed Argon2id verifier; treat the entire file as credential material. |
| `account.lock` | Persistent, empty, service-owned mode0600 single-link file with a separate exclusive flock. The command never unlinks or replaces its inode. |
| `admin-account.next` | Exclusive mode0600 staging file used for publication. A leftover at command entry causes refusal, including for status. |

The ready account record must be a regular, single-link file; symlinks, hardlinks,
unsafe modes and mount substitutions refuse. Init uses no-clobber link/unlink
publication; replacement checks exact expected old bytes and custody, then uses
atomic rename. The helper syncs the new file and parent and verifies the final
record. A failure during init can leave two names for the same inode; do not
change link counts or delete one to make validation pass.

An owned helper retains the instance/worker exclusion and account lock through
actual exit. The foreground command waits for it. Closing input before submission
aborts an unsubmitted helper, but a helper that received the credentials can
finish hashing/publication **after the foreground parent dies**. Interrupting the
parent or losing its result does not prove cancellation or rollback. An interrupt
after submission waits for helper completion and reports an uncertain outcome.

For an `outcome uncertain` message, lost result or stale staging refusal:

1. Preserve the original state, configuration and all account files; wait for
   actual helper/worker exit. Do not force a replacement or remove either lock.
2. Use `--admin-account-status` with the same original configuration/directory
   once exclusion permits it. If staging/custody is unsafe, status also refuses;
   keep that evidence for review.
3. Treat status as the current record observation, not a historical command
   receipt or proof of crash durability. Review the outcome before any deliberate
   next action. There is no automatic retry, restore, staging adoption, account
   repair or reset command in this slice.

## Recover the terminal after an abnormal exit

During prompting, Ctrl-C, Ctrl-D or Ctrl-Z abort input; catchable interrupt,
terminate, hangup, quit and suspend signals also take the restoration path. Normal
completion, mismatch and prompt timeout restore the saved terminal settings.
Tested interruption/restoration cases and limits are recorded in
[increment128](RUST-INCREMENT-128.md).

SIGKILL and process/host crashes cannot run restoration. Once your shell has
regained the foreground terminal, restore conventional terminal behavior with:

```sh
stty sane < /dev/tty
```

If Enter is not recognized, finish that shell command with Ctrl-J. Do not type it
into a still-active password prompt. `stty sane` sets conventional settings; it
cannot recover every custom previous setting. Reopen the terminal if necessary.
Terminal repair does not cancel a submitted helper, settle publication or release
instance ownership. Apply the uncertain-outcome procedure above before retrying.

Account setup does not start an HTTP/admin listener, create sessions, invalidate
live sessions or authorize remote password changes. Browser/session integration,
deployment, offline-bundle/shipping qualification and all eight FR release gates
remain separate and open. Use increment128 for the completed bounded SLES checks
and independent review.
