"""Regression checks for full-parent coverage and conservative L1 roll-ups."""
import unittest
from unittest.mock import patch

import trace_l1


class CoverageTests(unittest.TestCase):
    def rollup(self, disposition="Tested", parent="L1-SYS-006"):
        l1 = f"### {parent}\n"
        l2 = f"#### L2-COPY-007\n\n**Parent**: {parent}\n"
        trace = f"| L2-COPY-007 | {disposition} | | Backlog (approved 2026-11-22) |\n"
        return trace_l1.generate(l1, l2, trace)

    def test_known_configurable_integrity_gap_cannot_be_traced(self):
        for disposition in ["Tested", "Out of scope (approved)"]:
            with self.subTest(disposition=disposition):
                text, counts = self.rollup(disposition)
                self.assertEqual(counts["Traced"], 0)
                self.assertEqual(counts["Partly traced"], 1)
                self.assertIn("COPY-007 covers byte counts", text)
                self.assertIn("not configurable integrity verification", text)

    def test_unreviewed_parent_cannot_be_traced(self):
        with patch.object(trace_l1, "COVERAGE_GAPS", {}):
            text, counts = self.rollup(parent="L1-SYS-001")
        self.assertEqual(counts["Traced"], 0)
        self.assertIn("Full parent coverage not reviewed", text)

    def test_reviewed_coverage_still_requires_complete_children(self):
        with patch.object(trace_l1, "COVERAGE_GAPS", {}), patch.object(
            trace_l1, "COVERAGE_CONFIRMED", {"L1-SYS-006": "Synthetic complete coverage review."}
        ):
            for disposition, expected in [
                ("Tested", "Traced"),
                ("Out of scope (approved)", "Traced"),
                ("Inspection", "Partly traced"),
                ("Partly tested", "Partly traced"),
                ("Open", "Backlog"),
                ("Deviation (needs approval)", "Backlog"),
            ]:
                with self.subTest(disposition=disposition):
                    _, counts = self.rollup(disposition)
                    self.assertEqual(counts[expected], 1)

    def test_known_gap_and_coverage_confirmation_cannot_coexist(self):
        with patch.object(trace_l1, "COVERAGE_CONFIRMED", {"L1-SYS-006": "Conflicting review."}):
            with self.assertRaisesRegex(ValueError, "known incomplete"):
                self.rollup()

    def test_missing_derivation_is_backlog_not_a_vacuous_pass(self):
        with patch.object(trace_l1, "COVERAGE_GAPS", {}):
            text, counts = trace_l1.generate(
                "### L1-SYS-001\n### L1-SYS-002\n",
                "#### L2-COPY-007\n\n**Parent**: L1-SYS-001\n",
                "| L2-COPY-007 | Tested | | Count evidence |\n",
            )
        self.assertEqual(counts["Backlog"], 1)
        self.assertIn("None — missing L2 derivation | Backlog", text)

    def test_unknown_or_empty_coverage_review_is_rejected(self):
        for review in [{"L1-SYS-999": "Unknown parent."}, {"L1-SYS-006": ""}]:
            with self.subTest(review=review), patch.object(trace_l1, "COVERAGE_GAPS", {}), patch.object(
                trace_l1, "COVERAGE_CONFIRMED", review
            ):
                with self.assertRaises(ValueError):
                    self.rollup()


if __name__ == "__main__":
    unittest.main()
