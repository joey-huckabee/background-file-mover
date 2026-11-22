#!/usr/bin/env python3
"""Check pending L2 decision assignments; never change requirements or dispositions."""
from collections import Counter
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
APPROVAL = {"Deviation (needs approval)", "Not applicable (needs approval)"}
ID = r"L2-[A-Z]+-\d{3}"


def check(trace: str, sheet: str) -> list[str]:
    rows = {}
    for line in trace.splitlines():
        if line.startswith("| L2-"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) == 4:
                rows[cells[0]] = cells[1]
    expected = {i for i, disposition in rows.items() if disposition in APPROVAL}
    errors, assignments, decisions = [], [], []
    sections = re.findall(r"^## (D\d{2}) — [^\n]+\n(.*?)(?=^## |\Z)",
                          sheet, re.M | re.S)
    for decision, body in sections:
        decisions.append(decision)
        lines = re.findall(r"^\*\*Approval-needed IDs:\*\* (.+)$", body, re.M)
        ids = re.findall(ID, lines[0]) if len(lines) == 1 else []
        if not ids:
            errors.append(f"{decision}: missing or ambiguous approval list")
        assignments.extend((ident, decision) for ident in ids)
    if not decisions or len(decisions) != len(set(decisions)):
        errors.append("missing or duplicate decision sections")

    def table(heading: str, end: str) -> list[tuple[str, str]]:
        if sheet.count(heading) != 1:
            errors.append(f"missing or duplicate heading: {heading}")
            return []
        block = sheet.split(heading, 1)[1].split(end, 1)[0]
        return re.findall(rf"^\| ({ID}) \| (D\d{{2}}) \|", block, re.M)

    index = table("## Approval ID index\n", "## Self-check\n")
    pending = table("## Pending items outside the 79 approval rows\n",
                    "## Approval ID index\n")
    for label, pairs in [("section lists", assignments), ("approval index", index)]:
        counts = Counter(ident for ident, _ in pairs)
        duplicates = sorted(ident for ident, count in counts.items() if count > 1)
        if duplicates:
            errors.append(f"{label}: duplicate IDs {duplicates}")
        if set(counts) != expected:
            errors.append(f"{label}: missing {sorted(expected - set(counts))}; "
                          f"extra {sorted(set(counts) - expected)}")
    if Counter(assignments) != Counter(index):
        errors.append("approval index and section assignments differ")
    if len(pending) != len({ident for ident, _ in pending}):
        errors.append("duplicate supplementary pending IDs")
    for ident, decision in index + pending:
        if decision not in decisions:
            errors.append(f"{ident}: unknown decision {decision}")
    for ident, _ in pending:
        if ident not in rows or ident in expected:
            errors.append(f"{ident}: supplementary ID must exist outside approval set")
    return errors


def main() -> int:
    trace = (ROOT / "docs/TRACE-L2.md").read_text(encoding="utf-8")
    sheet = (ROOT / "docs/TRACE-DECISIONS.md").read_text(encoding="utf-8")
    errors = check(trace, sheet)
    for error in errors:
        print(f"ERROR: {error}")
    if not errors:
        print("Decision sections and index exactly match the approval-needed L2 IDs")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
