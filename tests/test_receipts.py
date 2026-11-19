from decimal import Decimal
import unittest

from receipt_review.evaluate import choose_thresholds, normalize
from receipt_review.extract import extract
from receipt_review.ocr import Line, read_tsv


def lines(*texts):
    return [Line(text, 0.98, (1, 2, 10, 20)) for text in texts]


class ReaderTests(unittest.TestCase):
    def test_money_evidence_and_total_selection(self):
        result = extract(lines("LITTLE MART", "Date 19/11/2026", "Subtotal 1,000.15",
                               "GRAND TOTAL 1,000.15", "Cash tendered 1,010.00"))
        self.assertEqual(result["fields"]["total"]["value"], "1000.15")
        self.assertEqual(result["fields"]["total"]["evidence"]["bbox"], (1, 2, 10, 20))
        self.assertEqual(result["fields"]["date"]["value"], "2026-11-19")
        self.assertEqual(result["arithmetic"]["status"], "matches")

    def test_negative_printed_discount_counts_once(self):
        result = extract(lines("Subtotal 10.10", "Tax 0.20", "Service fee 0.30",
                               "Discount -0.40", "Grand total 10.20"))
        self.assertEqual(result["arithmetic"]["difference"], "0.00")

    def test_mismatch_surfaces_and_preserves_printed_total(self):
        result = extract(lines("Subtotal 19.95", "Tax 0.55", "Grand Total 21.50"))
        self.assertEqual(result["arithmetic"]["status"], "mismatch")
        self.assertEqual(result["arithmetic"]["difference"], "1.00")
        self.assertEqual(result["fields"]["total"]["value"], "21.50")
        self.assertTrue(any("reconcile" in q for q in result["questions"]))

    def test_competing_totals_require_review(self):
        result = extract(lines("Subtotal 19.95", "Total 20.50", "Total 21.50"))
        self.assertIn("competing_values", result["fields"]["total"]["reasons"])
        self.assertEqual(result["arithmetic"]["status"], "unavailable")

    def test_tax_inclusion_blocks_arithmetic(self):
        result = extract(lines("Subtotal 10.00", "Incl tax", "Tax 0.50", "Grand Total 10.00"))
        self.assertEqual(result["arithmetic"]["status"], "unavailable")

    def test_unreadable_adjustment_is_not_assumed_zero(self):
        result = extract(lines("Subtotal 10.00", "Discount ?", "Grand Total 10.00"))
        self.assertEqual(result["fields"]["discount"]["reasons"], ["label_without_amount"])
        self.assertEqual(result["arithmetic"]["status"], "unavailable")

    def test_missing_and_low_score(self):
        result = extract([Line("Grand Total 12.90", 0.30)])
        self.assertEqual(result["fields"]["total"]["reasons"], ["low_score"])
        self.assertEqual(result["fields"]["date"]["reasons"], ["missing"])

    def test_decimal_evaluation_and_date_convention(self):
        self.assertEqual(normalize("total", "RM 1,005.50"), Decimal("1005.50"))
        self.assertEqual(extract(lines("Date 03/07/2026"), day_first=False)["fields"]["date"]["value"], "2026-03-07")
        self.assertIsNone(extract(lines("Date 31/02/2026"))["fields"]["date"]["value"])

    def test_tsv_coordinates_map_back_to_input(self):
        tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
               "5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t95\tTOTAL\n"
               "5\t1\t1\t1\t1\t2\t70\t20\t20\t10\t80\t11.00\n")
        self.assertEqual(read_tsv(tsv, 2, 2), [Line("TOTAL 11.00", 0.8, (5, 10, 45, 15))])

    def test_fit_abstains_when_precision_target_unattainable(self):
        row = {"truth": {"total": "10.30"}}
        fitted = choose_thresholds([(row, lines("TOTAL 12.90"))], minimum=1)
        self.assertEqual(fitted["total"], 1.01)


if __name__ == "__main__":
    unittest.main()
