# transcripts/ — staging area for design material awaiting integration

This directory holds design conversations and milestone artifacts produced
outside the repository that have **not yet been retired into the specs**.

It follows the precedent set by `docs/CAPTURE.md`, the original design
conversation for the Python implementation: land the raw material in-tree,
mine it into requirements and ADRs commit by commit, then delete it. Raw
transcript content never becomes reference documentation — the specs are the
reference, and this directory is scaffolding.

## Protocol

1. Drop a conversation export and/or milestone zip contents here.
2. Integrate each piece into its permanent home:
   - decisions → `docs/adr/`
   - requirements → `docs/L1-REQ.md`, `docs/L2-REQ.md`, `docs/L3-REQ.md`
   - code, build, CI → `cpp/`, `.github/workflows/`
3. **Delete each file from this directory as it is integrated.**
4. When this directory contains nothing but this README, the repository is
   **ready for the next milestone conversation and zip drop**.

An empty `transcripts/` is the ready signal. A non-empty one is a to-do list.

## Not yet integrated

| File | Blocked on |
|---|---|
| — | **Nothing. Ready for the next drop.** |

The first drop is fully retired. Where it ended up:

| Inherited material | Now lives in |
|---|---|
| Design conversation | ADR-0001 … ADR-0006, `cpp/README.md` |
| L1 system requirements | `docs/L1-REQ.md`, renumbered into `L1-SYS-*` / `L1-API-*` / `L1-OBS-*` |
| L2 component requirements | `docs/L2-REQ.md` — CORE, JSON, REN, MGR, XFR, DASH, plus a rewritten CTL |
| L3-CPP obligations | `docs/L3-REQ.md`, `L3-CPP-001..032` |
| Job state machine + tests | `cpp/src/job.cpp`, `cpp/tests/test_job.cpp` |
| Codec interface | `cpp/include/filemover/api_codec.hpp`, near-verbatim |
| Codec implementation | **Rewritten** on the project-owned parser (ADR-0006) |
| Codec tests | Rewritten; the picojson characterization suite died with picojson |
| Journal durability design | **Superseded** by ADR-0010 (SQLite); no retirement step needed |
| Milestone numbering (M1..M12) | Deliberately dropped — this repo tracks requirements, not inherited milestones |

## Caveat on inherited material

The originating conversation designed a standalone project from scratch and
did not know this repository's existing requirements, locked decisions, or
constraints. Material here is **triaged, not adopted wholesale**:

| Bucket | Action |
|---|---|
| ADOPT | New capability with no equivalent here |
| REDUNDANT | Re-derives an existing requirement — drop, map to the existing ID |
| CONFLICT | Contradicts an existing requirement — **repo wins by default** |
| SUPERSEDE | Genuinely better, with a written reason |
| DEFER | Good, but not v1.0.0 — goes to `docs/ROADMAP.md` |

Inherited material has already been found to contain at least one fabricated
premise (ADR-0001 cited a non-existent prior C++ implementation of this
project, corrected in place). Verify factual claims before promoting them
into a spec.
