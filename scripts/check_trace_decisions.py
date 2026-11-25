#!/usr/bin/env python3
"""Check recorded L2 decision assignments and approved backlog; never change requirements or dispositions."""
from collections import Counter
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
APPROVAL = {"Deviation (needs approval)", "Not applicable (needs approval)"}
ID = r"L2-[A-Z]+-\d{3}"
SUPERSEDED = {"L2-CLI-006": "**Superseding requirement (2026-11-23; settings 2026-11-25):**"}


def check(trace: str, sheet: str) -> list[str]:
    rows = {}
    for line in trace.splitlines():
        if line.startswith("| L2-"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) == 4:
                rows[cells[0]] = (cells[1], cells[3])
    expected = {i for i, (disposition, notes) in rows.items()
                if disposition in APPROVAL
                or "**Approved rewording (" in notes
                or (i in SUPERSEDED and SUPERSEDED[i] in notes)
                or disposition == "Out of scope (approved)"}
    errors, assignments, decisions = [], [], []
    choices = {}
    sections = re.findall(r"^## (D\d{2}) — [^\n]+\n(.*?)(?=^## |\Z)",
                          sheet, re.M | re.S)
    for decision, body in sections:
        decisions.append(decision)
        answer = "c" if decision == "D04" else "b" if decision in {"D10", "D11", "D12"} else "a"
        choices[decision] = answer
        marker = f"**Decided 2026-11-22: ({answer}) — user accepted the recommendation.**"
        if body.count(marker) != 1:
            errors.append(f"{decision}: missing or incorrect answer marker")
        lines = re.findall(r"^\*\*Original approval-needed IDs:\*\* (.+)$", body, re.M)
        ids = re.findall(ID, lines[0]) if len(lines) == 1 else []
        if not ids:
            errors.append(f"{decision}: missing or ambiguous approval list")
        assignments.extend((ident, decision) for ident in ids)
    if set(decisions) != {f"D{n:02}" for n in range(1, 13)} or len(decisions) != 12:
        errors.append("missing or duplicate decision sections")

    def table(heading: str, end: str) -> list[tuple[str, str]]:
        if sheet.count(heading) != 1:
            errors.append(f"missing or duplicate heading: {heading}")
            return []
        block = sheet.split(heading, 1)[1].split(end, 1)[0]
        return re.findall(rf"^\| ({ID}) \| (D\d{{2}}) \|", block, re.M)

    index = table("## Approval ID index\n", "## Self-check\n")
    pending = table("## Supplementary items outside the original 79 approval rows\n",
                    "## Approved backlog\n")
    expected -= {ident for ident, _ in pending}
    for label, pairs in [("section lists", assignments), ("approval index", index)]:
        counts = Counter(ident for ident, _ in pairs)
        duplicates = sorted(ident for ident, count in counts.items() if count > 1)
        if duplicates:
            errors.append(f"{label}: duplicate IDs {duplicates}")
        if set(counts) != expected:
            errors.append(f"{label}: missing {sorted(expected - set(counts))}; "
                          f"extra {sorted(set(counts) - expected)}")
    if len(expected) != 79:
        errors.append(f"original approval cohort must contain 79 IDs, got {len(expected)}")
    if Counter(assignments) != Counter(index):
        errors.append("approval index and section assignments differ")
    if len(pending) != 16:
        errors.append("supplementary cohort must contain 16 IDs")
    if len(pending) != len({ident for ident, _ in pending}):
        errors.append("duplicate supplementary pending IDs")
    for ident, decision in index + pending:
        if decision not in decisions:
            errors.append(f"{ident}: unknown decision {decision}")
    for ident, _ in pending:
        if ident not in rows or ident in expected or rows[ident][0] in APPROVAL:
            errors.append(f"{ident}: supplementary ID must exist outside approval set")
    for ident, decision in index + pending:
        if ident not in rows or decision not in choices:
            continue
        disposition, notes = rows[ident]
        if choices[decision] == "a":
            if disposition not in {"Tested", "Partly tested", "Inspection"}:
                errors.append(f"{ident}: accepted rewording needs evidence disposition")
            if SUPERSEDED.get(ident, f"**Approved rewording ({decision}, 2026-11-22):**") not in notes:
                errors.append(f"{ident}: missing approved requirement statement")
        elif choices[decision] == "c":
            if disposition != "Out of scope (approved)" or "first release; later inclusion needs separate approval" not in notes:
                errors.append(f"{ident}: missing approved first-release exclusion")
        elif f"**Backlog (approved 2026-11-22), {decision}:**" not in notes:
            errors.append(f"{ident}: missing approved backlog marker")
    # Backlog table has grouped IDs: retain every b-choice once, including supplementary items.
    heading = "## Approved backlog\n"
    if sheet.count(heading) != 1:
        errors.append("missing or duplicate Approved backlog heading")
        backlog = []
    else:
        block = sheet.split(heading, 1)[1].split("## Approval ID index\n", 1)[0]
        backlog = []
        for line in block.splitlines():
            cells = [c.strip() for c in line.strip("|").split("|")]
            if line.startswith("| ") and len(cells) == 4 and re.fullmatch(r"D\d{2}", cells[1]):
                backlog.extend((ident, cells[1]) for ident in re.findall(ID, cells[2]))
    wanted = [(ident, decision) for ident, decision in index + pending
              if choices.get(decision) == "b"]
    if Counter(backlog) != Counter(wanted):
        errors.append("approved backlog must contain every b-choice ID once with its decision")
    return errors


def main() -> int:
    trace = (ROOT / "docs/TRACE-L2.md").read_text(encoding="utf-8")
    sheet = (ROOT / "docs/TRACE-DECISIONS.md").read_text(encoding="utf-8")
    errors = check(trace, sheet)
    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        print("Original 79-ID cohort, 16 supplementary IDs, 12 answers and 21 backlog IDs match the trace")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
