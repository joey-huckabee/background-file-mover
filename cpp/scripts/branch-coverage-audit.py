#!/usr/bin/env python3
"""Separate the never-taken branches worth acting on from the ones the
compiler emitted.

Why this exists. gcov's branch data for C++ counts every exception-unwind edge
the compiler generates, and those cannot be taken by any test that does not
force an allocation failure. Measured across this tree, roughly three quarters
of never-taken branches sit on source lines containing no conditional at all --
`std::ostringstream os;`, `os << "store: " << what;`, `return fail(...)`.

A raw branch percentage therefore says almost nothing about test quality here:
it is dominated by an artifact. What is useful is the remaining quarter, which
is real logic no test reaches. This script reports the split so that number can
be acted on.

The heuristic is deliberately simple and slightly conservative: a never-taken
branch on a line with no `if`, `while`, `for`, `switch`, `case`, `?`, `&&` or
`||` is counted as compiler-emitted. It can misclassify a conditional split
across lines, which inflates the "compiler-emitted" side -- so treat the
"worth acting on" figure as a lower bound rather than an exact count.

Usage:  python3 scripts/branch-coverage-audit.py <file.gcov> [...]
"""
import re
import sys

SRC = re.compile(r"^\s*([#\-0-9]+):\s*(\d+):(.*)$")
COND = re.compile(r"(\bif\b|\bwhile\b|\bfor\b|\bswitch\b|\bcase\b|\?|&&|\|\|)")


def audit(path):
    line_no = 0
    source = ""
    never = []

    with open(path, encoding="utf-8", errors="replace") as handle:
        for raw in handle:
            raw = raw.rstrip("\n")
            match = SRC.match(raw)
            if match:
                line_no = int(match.group(2))
                source = match.group(3)
                continue
            if raw.startswith("branch") and (
                "never executed" in raw or "taken 0%" in raw
            ):
                never.append((line_no, source.strip()))

    real = [x for x in never if COND.search(x[1])]
    emitted = [x for x in never if not COND.search(x[1])]
    return never, real, emitted


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2

    total = total_real = total_emitted = 0
    for path in argv[1:]:
        never, real, emitted = audit(path)
        total += len(never)
        total_real += len(real)
        total_emitted += len(emitted)

        name = path.rsplit("/", 1)[-1]
        print("%-24s never-taken: %4d   worth acting on: %4d   emitted: %4d"
              % (name, len(never), len(real), len(emitted)))
        for line_no, source in real[:5]:
            print("      %5d: %s" % (line_no, source[:80]))

    if len(argv) > 2:
        print()
        print("TOTAL  never-taken: %d   worth acting on: %d   emitted: %d"
              % (total, total_real, total_emitted))
        if total:
            print("       %.0f%% of never-taken branches are compiler-emitted"
                  % (100.0 * total_emitted / total))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
