# Dashboard concept 01: Control room

Open [mockup.html](mockup.html) directly in a browser. Keep `mockup.css` and
`mockup.js` beside it. No installation, build, server, CDN, external fonts,
libraries or internet access is needed. All icons are original inline SVG.

This is an interactive design proposal, not the production dashboard. It never
contacts the service, writes a file, persists credentials or changes real work.
Refresh the page to reset the fictional jobs. Do not enter real credentials.

## Explore the mockups

1. **Overview:** retained-work summary, custody/delivery/commitment distribution,
   exceptions and recent jobs. Reservation meters are explicitly ledger values,
   not disk usage. The concept totals represent a larger fictional dataset.
2. **Job history:** search the eight sample jobs, filter states, select rows and
   inspect bulk actions. Pagination controls deliberately do not pretend there
   are more loaded samples. The production API must provide bounded paging.
3. **Needs attention:** open job 1047. Inspect the condition and add an audit
   explanation before simulated retry. There is no extra retry confirmation.
4. **Job detail:** file phases, custody, original UUID, routing and illustrative
   milestones. Progress represents file states, never invented byte telemetry.
5. **Retention:** distinguish accounted reservations, history forgetting and
   physical deletion. No filesystem scan or post-clear inventory is promised.
6. **Clear history:** select committed job 1045, then Clear history. The dialog
   explains preserved files, UUID forgetting and loss of every mover link.
7. **Cancellation:** select an unfinished job. Confirmation lists the selected
   jobs; the simulated result remains pending rather than claiming safe stop.
8. **Delete owned data:** select cancelled job 1042. Review an exact three-file
   illustrative scope and explicit irreversible-deletion acknowledgement.
   No real filesystem operation occurs; the result only simulates acceptance.
9. **Sign-in:** use the sidebar sign-out button. Preview invalid credentials or
   enter the console without providing credentials. Account management remains
   host-local; there is no remote password-reset proposal.
10. **Unavailable/stale:** cycle the preview control in the top strip. Preserve
    the last known snapshot, identify its age/state and disable mutations.

## Visual direction

Forest-green navigation, warm ivory canvas, restrained lime highlights and
amber exceptions create a calm operational workspace. Status always has a text
label. Original line icons, tabular figures, fine dividers and generous spacing
make dense operational data easier to scan. Local system fonts avoid deployment
and licensing dependencies. Responsive CSS collapses navigation and stacks
panels on narrow windows; tables retain horizontal scrolling.

## Backend and design boundaries

The approved contract is [the API closeout](../api/API-CONTRACT-CLOSEOUT.md),
not this simulation. No new public route, metric or action is authorized here.
Display names, aggregate counts, accepted-time labels, milestones, search and
filtering are presentation proposals requiring field-by-field mapping before
backend work. Missing persisted measurements must display as unknown. Production
must derive authoritative eligibility, receipts, exact deletion scope and
confirmation freshness on the server, never from browser sample state.

| Screen/flow | Production integration still needed |
|---|---|
| Sign-in and sign-out | Host-local account setup, authenticated admin HTTPS boundary, cookies, CSRF, inactivity and global revocation |
| History and overview | Bounded list/read contracts; exact available fields, aggregation and ordering; no unbounded client-side scan |
| Detail and retention | Authorized current status/ledger reads; explicit missing/unavailable/partial values; exact serialized sizes |
| Retry | Frozen reviewed epoch/audit context, authenticated exact replay, atomic per-occurrence outcomes |
| Cancel | Durable cancellation intent, admission serialization and actual effect settlement |
| Clear | Fresh confirmation, eligible settled jobs only, complete per-job forgetting without payload effects |
| Delete | Complete exact-object preview, stale-proof rejection, owned-data checks, asynchronous pass/results and deliberate subsequent confirmation |

The eventual production UI must use DOM text nodes/textContent for untrusted
paths and errors. This isolated mockup renders escaped fictional values through
templates; it is not a reviewed production rendering implementation. Production
also needs bounded single-flight polling, stale-response exclusion, accessible
focus/error announcements, inactivity behavior excluding background refresh,
lost-response handling, and keyboard/mobile/contrast qualification.

## Review performed

JavaScript syntax and Git whitespace checks pass. The overview rendered in the
local Chrome browser and its accessibility tree exposed the expected content.
Visual inspection caught CSP-blocked inline widths; these were replaced with
stylesheet classes. A later browser-control safety check could not confidently
identify the active URL and ended computer use. The revised layout and remaining
interactive screens have not received a complete browser verification pass.
No backend, Rust, dependency, build, installation or production-state changes.

This branch is a reviewable design draft. It is not merged or release-qualified.
