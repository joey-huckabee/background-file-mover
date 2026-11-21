# Increment 169: supported deployment and qualification matrix (DOC-05)

2026-11-21, continuing release gate P10-11 while the user is unavailable.
Documentation only; no behavior change.

## Change

- New [supported deployment and qualification matrix](SUPPORTED-DEPLOYMENT.md).
  It covers platform, storage, network and access, installation and lifecycle,
  and the features that change data. Each row carries a status (Gated, Tested
  or Open) and links its evidence.
- **Stale status lines corrected** in [DEPLOYMENT.md](DEPLOYMENT.md) and
  [USER-GUIDE.md](USER-GUIDE.md):
  - They said migration apply and UUID/manifest-v2 activation "remain
    disabled". Both are implemented (increments 115 and 118), as
    [TESTING-LIMITATIONS.md](TESTING-LIMITATIONS.md) already stated.
  - "Source deletion" is now worded as move mode and confirmed data deletion,
    which exist and are off by default.
- Links from the user guide, deployment index, scenarios DOC-05 row and the
  roadmap.

## How it was checked

Every row restates an existing source:
- the SLES gate (pinned inputs, both modes, container-only SLES userspace);
- the offline install (bundle contents, candidate unit with `Restart=no`,
  installer refusing qualification executables, rollback limits);
- the operator guide (admitted state filesystems, protected ingress, move
  mode);
- the HTTPS client guide (TLS 1.2/1.3, tested curl and OpenSSL versions);
- AGENTS.md (four admin connections, loopback never a TLS fallback);
- the offline migration (schemas 11-17 to 18);
- increments 143/160 (deletion, one job per request).

The browser note records only what this session used (headless Microsoft
Edge).

## Not covered

- No new qualification; all eight release gates remain open.
- L1/L2/L3 traceability (the rest of P10) remains open.
