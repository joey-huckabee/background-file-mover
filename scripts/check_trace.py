#!/usr/bin/env python3
"""Check docs/TRACE-L2.md: IDs exist in L2-REQ.md, cited files exist, each cited
`file::name` is a function marked #[test], dispositions are allowed and no L2 ID
is mapped twice. `scripts/...` references (CI tests in other languages) are
checked for existence only. Prints a summary. It checks references only; whether a test
really demonstrates its row is a review question."""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CRATES = ROOT / "rust" / "crates"
ALLOWED = {
    "Tested", "Partly tested", "Inspection", "Deviation (needs approval)",
    "Not applicable (needs approval)", "Out of scope (approved)", "Open",
}


def is_test(source: str, name: str) -> bool:
    """True when `fn name(` exists and its attribute block includes #[test]."""
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if re.match(rf"\s*(pub(\([^)]*\))?\s+)?fn {re.escape(name)}\s*\(", line):
            j = i - 1
            while j >= 0 and re.match(r"\s*(#\[|///|//)", lines[j]):
                if re.match(r"\s*#\[test\]", lines[j]):
                    return True
                j -= 1
    return False


def main() -> int:
    requirements = set(re.findall(r"^#### (L2-[A-Z]+-\d{3})$",
                                  (ROOT / "docs" / "L2-REQ.md").read_text(encoding="utf-8"), re.M))
    errors, seen, counts = [], set(), {}
    for number, line in enumerate((ROOT / "docs" / "TRACE-L2.md").read_text(encoding="utf-8").splitlines(), 1):
        if not line.startswith("| L2-"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 4:
            errors.append(f"line {number}: expected 4 cells, got {len(cells)}")
            continue
        ident, disposition, evidence, notes = cells
        if ident not in requirements:
            errors.append(f"line {number}: {ident} is not in L2-REQ.md")
        if ident in seen:
            errors.append(f"line {number}: {ident} mapped twice")
        seen.add(ident)
        if disposition not in ALLOWED:
            errors.append(f"line {number}: unknown disposition {disposition!r}")
        counts[disposition] = counts.get(disposition, 0) + 1
        if not notes:
            errors.append(f"line {number}: notes are required")
        refs = [r.strip() for r in evidence.split(";") if r.strip()]
        if disposition not in ("Open", "Not applicable (needs approval)", "Out of scope (approved)") and not refs:
            errors.append(f"line {number}: {disposition} needs evidence")
        for ref in refs:
            path, _, test = ref.partition("::")
            if path.startswith("scripts/"):
                # Repository scripts (for example dashboard JavaScript tests):
                # existence only; they run in the hygiene CI job.
                if test or not (ROOT / path).is_file():
                    errors.append(f"line {number}: no script {path} (no ::name allowed)")
                continue
            file = CRATES / path
            if not file.is_file():
                errors.append(f"line {number}: no file {path}")
                continue
            if test and not is_test(file.read_text(encoding="utf-8"), test):
                errors.append(f"line {number}: no #[test] fn {test} in {path}")
    for e in errors:
        print("ERROR:", e)
    print(f"{len(seen)} of {len(requirements)} L2 requirements mapped: " +
          ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
