# Rust increment 39: remote API access contract

Documentation/design increment on `feature/rust-transfer-coordinator`, 2026-10-16.
Defines [the remote producer contract](REMOTE-API-ACCESS-CONTRACT.md) for FR-01.
Registration and bearer-token issuance remain deferred; their selected future
one-time setup key is unchanged. No remote ingress, TLS, peer-credential code,
configuration, dependency, schema or runtime behavior is implemented here.

The proposed first profile uses manually provisioned client certificates verified
and explicitly approved by an external same-host proxy. A protected producer-only
Unix socket plus proxy UID/principal checks bind the authorized generator; body
identity and source permissions must agree. Producer ingress permits only exact
recording submission, never status/retention/operator/registration routes. Current
runtime remains loopback with its existing header behavior. A reverse proxy in
front of that existing listener is not implementation of this boundary.

The design preserves the recorder JSON, optional sizes, explicit subfolders,
startup destination, 202-after-all-claims and same-ID retry with no polling duty.
It distinguishes TLS/edge failures from mover responses, prohibits fabricated
success or proxy POST retries and keeps accepted work after credential revocation.
It defines controlled manual certificate rotation, trust/UID limits, proposed
bounded request budgets and sixteen finite pending RA cases. Five new stable
situations SC-082–086 cover spoofing, producer/operator separation, credential
lifecycle, lost proxy responses and local proxy bypass; SC-043 is refined.
There are 86 stable scenarios and six DOC items; none of the new scenarios is
promoted to implemented/qualified. DOC-01/05 obligations include remote setup and
confinement; the contract is not a finished remote quickstart.

L1-SEC-008 gains additive remote authorization obligations without reusing or
renumbering another requirement. Its historical v1.0.0 Deferred annotation and
all prior requirement IDs remain unchanged. API/registration/security notes,
README, release checklist, future-only roadmap and handoffs link the design.
The obsolete requirement that registration must precede every remote profile
is replaced by profile-specific qualification; anonymous fallback stays forbidden.

## Validation and limits

Review compared configuration/identity checks, request handling, loopback listener
validation, strict HTTP bounds and existing responses against current Rust source.
Official NGINX SSL/proxy documentation and Linux unix(7) were checked for the
external TLS/proxy/socket primitives and are linked in the contract. This validates
mechanism availability, not a composed secure deployment or a supported package
on SLES. Exact proxy package, certificate allowlist, UID/socket confinement,
producer-only listener, real-client interoperability and all RA tests remain open.

Documentation checks pass for 362 local Markdown links, consistent table columns,
the JSON submission, sixteen
unique RA cases, 86 unique stable scenario IDs, six DOC items, unchanged Rust and
scripts, trace consistency and whitespace. No Rust build/test or container fixture
was run for this documentation-only change; increment 38 remains current runtime
evidence. Production NFS and deletion remain disabled. FR-01/03 remain open;
next resolve NFS authority/fencing and select the exact remote deployment profile
before dependent ingress implementation and end-to-end qualification.
