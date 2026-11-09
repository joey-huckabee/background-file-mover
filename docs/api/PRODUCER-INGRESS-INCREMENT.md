# Next bounded implementation: protected local producer ingress

Current direction (2026-11-08): PR9 implements/qualifies this local Unix slice.
The user subsequently requires native HTTPS in Rust with no proxy.
[Native HTTPS plan](../NATIVE-HTTPS-PLAN.md) supersedes the future proxy/TLS
deployment portion below; the qualified local transport remains a separate mode.

Defined 2026-11-08, increment 120. Implements the P02 portion of RA-01/03/04/05/08
after [contract closeout](API-CONTRACT-CLOSEOUT.md). This is the next implementation
specification, not a claim that ingress is implemented or remotely deployable.
P03 selects/configures/qualifies TLS and certificate administration separately.

## Result

Add an opt-in Linux pathname Unix HTTP producer listener using existing crates.
Read `SO_PEERCRED` before accepting caller context, require the configured
dedicated non-root proxy UID, then require exactly one
`X-File-Mover-Generator` equal to the configured generator and request generator.
The proxy overwrites/removes incoming identity headers at its own boundary;
the backend does not trust a header from an unauthorized peer.

Permit only POST `/api/v2/jobs`. Reject all other paths without disclosing job
existence, and other methods with 405/Allow as appropriate. Keep exact producer
body/envelopes, immutable replay, path/claim safety and manifest publication.
No new producer credential, public operation ID or old-wire adapter is added.

## Configuration and endpoint custody

Absent configuration preserves the existing explicit loopback prototype mode.
Protected mode must disable its TCP listener entirely, not leave an alternative
unauthenticated POST route or operator interface reachable by the proxy UID.
Add a separate private host-local HTTP operator socket for existing reads,
specialized commands and health. It is accessible only to the mover account;
the producer UID cannot reach it. The existing control.sock stop/status protocol
stays independent of SQLite, NFS and admission queues.

Require explicit absolute producer/operator socket paths, proxy UID/GID and the
configured generator. Proxy UID must be non-root and distinct from the mover.
Use preprovisioned local directories, distinct from source/destination custody:
both ingress parents must be disjoint from the local state directory as well
as source/destination scopes. Producer parent owned by mover, mode 0750, dedicated
proxy group; producer socket
0660, matching owner/group. Operator parent stays mover-private 0700 and socket
0600. Do not create users/groups, install a service, chmod foreign files or gain
privileges. The deployed mover account must already have the permissions/group
membership needed to create that socket. Test this prerequisite explicitly.

Validate local storage, all ancestor custody, no symlink/mount aliases or writable
untrusted ancestors, and lexical/runtime separation before readiness. Preserve
instance/lifetime admission before SQLite or payload work. Keep descriptors
close-on-exec so worker subprocesses do not inherit ingress listeners.

Never blindly unlink an existing endpoint. For the initial increment, existing
names, foreign type/owner/group/mode, live listeners and unproven stale sockets
refuse before effects. Clean shutdown removes only this process's newly created
socket after rechecking its original device/inode under the validated parent.
Crash-leftover refusal must be documented as a limitation; no unqualified stale
socket repair command or lock/epoch deletion is introduced. Supported automatic
restart after such crashes needs a separately reviewed ownership/recovery
mechanism before the shipping lifecycle gate can close.

## Bounds and failure behavior

Share the existing eight HTTP-connection budget, allowing at most six producer
requests and reserving two for local operations. Refuse excess producer work
with the contract's 429/one-second retry guidance. No unbounded accept/task/body
queue, temporary request body file or automatic POST retry. Preserve 8 KiB/64
header and 64 KiB body bounds, strict framing, five-second read budget and the
existing ten-second claim/probe handoff window.

Wrong peer or missing/duplicate/mismatching proxy identity fails before Store
lookup, source access or allocation. Use the fixed producer error envelope and
the frozen route/context validation precedence; transport-level failures can
terminate before JSON. Trusting UID does not identify a particular executable
or protect against compromised proxy/same-UID/root administrators.

Shutdown stops new admission on both sockets without resetting the first
monotonic deadline. Already admitted transfers remain service-owned. Hold
existing guard/lifetime coverage through all SQLite threads and worker exit;
never infer NFS settlement from closing a listener.

## Concrete acceptance and delivery

- Default prototype mode unchanged; protected mode has no TCP fallback.
- Real Unix peer credentials: permitted distinct proxy UID succeeds; wrong UID,
  root, absent/duplicate/spoofed principal and generator mismatch refuse before
  any new SQL/job/file effect. Use disposable container accounts, no host changes.
- Producer route/method isolation, private operator access and independently
  responsive control.sock under producer saturation or a blocked handoff.
- Missing/unsafe/aliased parents and existing socket/file/symlink names refuse
  without overwrite. Clean shutdown cannot unlink a substituted name. Crash
  leftovers refuse with useful operator guidance and original state intact.
- Actual UUID handoff, lost-response replay/permutation, legacy recovery and
  source-path reuse over the new transport retain original receipts/v2 bytes.
- Stop/restart, bounded resources, inherited descriptor audit and original
  instance exclusion. Existing production NFS/deletion controls stay off.

Use one short-lived branch, coordinator plus independent reviewer and the single
WSL queue. No new project dependency without user approval. Every Rust build/test
uses both cargo-libc/SLES gate modes, GNU/glibc 2.22 ELF audits and exact-target
tests; no host-only substitute. Record actual results and update the operator
guide/scenario catalog before a reviewed merge. This increment alone cannot
close FR-01, FR-05 or shipping security/lifecycle gates.
