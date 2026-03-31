"""Unit tests for the bank statement engine."""

import csv
import os
import tempfile
import unittest

from bank_statement_engine.engine import (
    parse_csv,
    validate_balances,
    insert_and_recalculate,
    filter_by_date_range,
    write_csv,
    _parse_amount,
    _parse_date,
    _compute_opening_balance,
)


def _make_csv(rows_data, path):
    """Write a test CSV from list of (date, desc, credit, debit, balance) tuples."""
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Description", "Credit", "Debit", "Balance"])
        for row in rows_data:
            writer.writerow(row)


def _simple_statement():
    """
    A small newest-first statement for testing.
    Chronological order (oldest first):
        10/01/2026  Opening deposit   +1000   0    bal=1000  (opening=0)
        11/01/2026  Groceries           0    -200   bal=800
        12/01/2026  Salary            +5000   0    bal=5800
        13/01/2026  Rent                0   -2000   bal=3800
        14/01/2026  Coffee              0     -50   bal=3750

    Newest-first (as in CSV):
        14/01/2026  Coffee              0     50   3750
        13/01/2026  Rent                0   2000   3800
        12/01/2026  Salary           5000      0   5800
        11/01/2026  Groceries           0    200    800
        10/01/2026  Opening deposit  1000      0   1000
    """
    return [
        ("14/01/2026", "Coffee", "", "50", "3750"),
        ("13/01/2026", "Rent", "", "2000", "3800"),
        ("12/01/2026", "Salary", "5000", "", "5800"),
        ("11/01/2026", "Groceries", "", "200", "800"),
        ("10/01/2026", "Opening deposit", "1000", "", "1000"),
    ]


class TestParseAmount(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(_parse_amount("57.00"), 57.0)

    def test_comma_formatted(self):
        self.assertEqual(_parse_amount('"18,076.06"'), 18076.06)

    def test_empty(self):
        self.assertEqual(_parse_amount(""), 0.0)

    def test_none(self):
        self.assertEqual(_parse_amount(None), 0.0)

    def test_large_with_commas(self):
        self.assertEqual(_parse_amount('"1,00,000.00"'), 100000.0)


class TestParseDate(unittest.TestCase):
    def test_four_digit_year(self):
        dt = _parse_date("04/02/2026")
        self.assertEqual(dt.day, 4)
        self.assertEqual(dt.month, 2)
        self.assertEqual(dt.year, 2026)

    def test_two_digit_year(self):
        dt = _parse_date("27/03/26")
        self.assertEqual(dt.day, 27)
        self.assertEqual(dt.month, 3)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            _parse_date("not-a-date")


class TestParseCsv(unittest.TestCase):
    def test_parse_simple(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Description", "Credit", "Debit", "Balance"])
            writer.writerow(["14/01/2026", "Coffee", "", "50", "3750"])
            writer.writerow(["10/01/2026", "Deposit", "1000", "", "1000"])
            path = f.name

        try:
            rows = parse_csv(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["credit"], 0.0)
            self.assertEqual(rows[0]["debit"], 50.0)
            self.assertEqual(rows[0]["balance"], 3750.0)
            self.assertEqual(rows[1]["credit"], 1000.0)
        finally:
            os.unlink(path)


class TestValidateBalances(unittest.TestCase):
    def test_valid_statement(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            errors = validate_balances(rows)
            self.assertEqual(errors, [])
        finally:
            os.unlink(path)

    def test_invalid_statement(self):
        data = [
            ("14/01/2026", "Coffee", "", "50", "9999"),  # wrong balance
            ("10/01/2026", "Deposit", "1000", "", "1000"),
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(data, f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            errors = validate_balances(rows)
            self.assertTrue(len(errors) > 0)
        finally:
            os.unlink(path)


class TestSimpleInsert(unittest.TestCase):
    """Insert one credit, verify all downstream balances shift by exactly the credit amount."""

    def test_simple_insert(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            original_balances = [r["balance"] for r in rows]

            new_txns = [{
                "date": "11/01/2026",
                "description": "BONUS",
                "credit": 500.0,
                "debit": 0.0,
                "position": "top_of_date",
            }]

            updated = insert_and_recalculate(rows, new_txns)

            # One more row
            self.assertEqual(len(updated), 6)

            # All rows dated 12/01 and later should have balance increased by 500
            for row in updated:
                if row["_date"] >= _parse_date("12/01/2026") and not row.get("_injected"):
                    # Find the original balance for this description
                    for orig in zip(original_balances, _simple_statement()):
                        if orig[1][1] == row["description"]:
                            self.assertAlmostEqual(row["balance"], orig[0] + 500.0, places=2)

            # The injected row itself
            injected = [r for r in updated if r.get("_injected")]
            self.assertEqual(len(injected), 1)
            self.assertAlmostEqual(injected[0]["credit"], 500.0)
        finally:
            os.unlink(path)


class TestMultipleInsertsSameDate(unittest.TestCase):
    """Two credits on same date, verify ordering and balance."""

    def test_two_on_same_date(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            new_txns = [
                {"date": "12/01/2026", "description": "BONUS A", "credit": 100.0, "debit": 0.0, "position": "top_of_date"},
                {"date": "12/01/2026", "description": "BONUS B", "credit": 200.0, "debit": 0.0, "position": "top_of_date"},
            ]
            updated = insert_and_recalculate(rows, new_txns)
            self.assertEqual(len(updated), 7)

            # Both bonuses should appear, total delta = 300
            closing_orig = 3750.0
            closing_new = updated[0]["balance"]
            self.assertAlmostEqual(closing_new, closing_orig + 300.0, places=2)
        finally:
            os.unlink(path)


class TestNoNegativeAfterInsert(unittest.TestCase):
    """After inserting salary credits, verify no negative balances."""

    def test_no_negatives(self):
        # Statement that goes negative without credit injection
        data = [
            ("13/01/2026", "Big Purchase", "", "900", "100"),
            ("12/01/2026", "Salary", "1000", "", "1000"),
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(data, f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            new_txns = [{
                "date": "12/01/2026", "description": "EXTRA INCOME",
                "credit": 5000.0, "debit": 0.0, "position": "top_of_date",
            }]
            updated = insert_and_recalculate(rows, new_txns)

            for row in updated:
                self.assertGreaterEqual(row["balance"], 0.0)
        finally:
            os.unlink(path)


class TestOpeningBalancePreserved(unittest.TestCase):
    """Opening balance should not change after insertion."""

    def test_opening_preserved(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            chrono = list(reversed(rows))
            orig_opening = _compute_opening_balance(chrono)

            new_txns = [{
                "date": "12/01/2026", "description": "SALARY CREDIT",
                "credit": 50000.0, "debit": 0.0, "position": "top_of_date",
            }]
            updated = insert_and_recalculate(rows, new_txns)
            updated_chrono = list(reversed(updated))
            new_opening = _compute_opening_balance(updated_chrono)

            self.assertAlmostEqual(orig_opening, new_opening, places=2)
        finally:
            os.unlink(path)


class TestClosingBalanceIncreases(unittest.TestCase):
    """Closing balance should increase by sum of all inserted credits."""

    def test_closing_increases(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            orig_closing = rows[0]["balance"]  # newest row

            credits = [1000.0, 2000.0, 3000.0]
            new_txns = [
                {"date": "11/01/2026", "description": f"CREDIT {i+1}",
                 "credit": c, "debit": 0.0, "position": "top_of_date"}
                for i, c in enumerate(credits)
            ]
            updated = insert_and_recalculate(rows, new_txns)
            new_closing = updated[0]["balance"]

            self.assertAlmostEqual(new_closing, orig_closing + sum(credits), places=2)
        finally:
            os.unlink(path)


class TestRoundTrip(unittest.TestCase):
    """Parse → insert → write → parse again → balances match."""

    def test_round_trip(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            input_path = f.name

        output_path = input_path + ".out.csv"

        try:
            rows = parse_csv(input_path)
            new_txns = [{
                "date": "12/01/2026", "description": "ROUND TRIP TEST",
                "credit": 777.0, "debit": 0.0, "position": "top_of_date",
            }]
            updated = insert_and_recalculate(rows, new_txns)
            write_csv(updated, output_path)

            # Re-parse
            reparsed = parse_csv(output_path)
            self.assertEqual(len(reparsed), len(updated))

            for orig, re in zip(updated, reparsed):
                self.assertAlmostEqual(orig["balance"], re["balance"], places=2)
                self.assertAlmostEqual(orig["credit"], re["credit"], places=2)
                self.assertAlmostEqual(orig["debit"], re["debit"], places=2)
        finally:
            os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)


class TestBalanceContinuity(unittest.TestCase):
    """For every consecutive pair, balance[i] = balance[i+1] + credit[i] - debit[i]."""

    def test_continuity_after_insert(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            new_txns = [
                {"date": "11/01/2026", "description": "CREDIT A", "credit": 1000.0, "debit": 0.0, "position": "top_of_date"},
                {"date": "13/01/2026", "description": "CREDIT B", "credit": 2000.0, "debit": 0.0, "position": "top_of_date"},
            ]
            updated = insert_and_recalculate(rows, new_txns)
            errors = validate_balances(updated)
            self.assertEqual(errors, [], f"Balance continuity errors: {errors}")
        finally:
            os.unlink(path)


class TestIdempotency(unittest.TestCase):
    """Running insert twice with same inputs produces same output."""

    def test_idempotent(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            new_txns = [{
                "date": "12/01/2026", "description": "SALARY",
                "credit": 5000.0, "debit": 0.0, "position": "top_of_date",
            }]

            updated1 = insert_and_recalculate(rows, new_txns)
            # Run again on the already-updated result
            updated2 = insert_and_recalculate(updated1, new_txns)

            # Should not duplicate — same row count
            self.assertEqual(len(updated1), len(updated2))
            for r1, r2 in zip(updated1, updated2):
                self.assertAlmostEqual(r1["balance"], r2["balance"], places=2)
        finally:
            os.unlink(path)


class TestEmptyCsv(unittest.TestCase):
    """Handle empty CSV (just headers)."""

    def test_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Description", "Credit", "Debit", "Balance"])
            path = f.name

        try:
            rows = parse_csv(path)
            self.assertEqual(len(rows), 0)

            new_txns = [{
                "date": "01/01/2026", "description": "FIRST",
                "credit": 1000.0, "debit": 0.0, "position": "top_of_date",
            }]
            updated = insert_and_recalculate(rows, new_txns)
            self.assertEqual(len(updated), 1)
            self.assertAlmostEqual(updated[0]["balance"], 1000.0, places=2)
        finally:
            os.unlink(path)


class TestInsertBeforeEarliest(unittest.TestCase):
    """New transaction before the earliest existing date."""

    def test_before_earliest(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            orig_closing = rows[0]["balance"]

            new_txns = [{
                "date": "01/01/2026", "description": "EARLY DEPOSIT",
                "credit": 500.0, "debit": 0.0, "position": "top_of_date",
            }]
            updated = insert_and_recalculate(rows, new_txns)

            # Closing should increase by 500
            self.assertAlmostEqual(updated[0]["balance"], orig_closing + 500.0, places=2)

            # Balance continuity
            errors = validate_balances(updated)
            self.assertEqual(errors, [])
        finally:
            os.unlink(path)


# -----------------------------------------------------------------------
# Date Range Filtering Tests
# -----------------------------------------------------------------------

class TestFilterBasic(unittest.TestCase):
    """Filter to a date range, verify only matching rows returned."""

    def test_filter_middle(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            # Filter to 11/01 – 13/01 (should get Groceries, Salary, Rent)
            filtered, summary = filter_by_date_range(rows, "11/01/2026", "13/01/2026")

            self.assertEqual(len(filtered), 3)
            self.assertEqual(summary["transaction_count"], 3)

            # Newest-first in filtered output
            self.assertEqual(filtered[0]["description"], "Rent")
            self.assertEqual(filtered[-1]["description"], "Groceries")
        finally:
            os.unlink(path)

    def test_filter_single_date(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            filtered, summary = filter_by_date_range(rows, "12/01/2026", "12/01/2026")

            self.assertEqual(len(filtered), 1)
            self.assertEqual(filtered[0]["description"], "Salary")
        finally:
            os.unlink(path)


class TestFilterBalancesCorrect(unittest.TestCase):
    """Filtered output must have valid, self-contained balances."""

    def test_balance_continuity(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            filtered, summary = filter_by_date_range(rows, "11/01/2026", "14/01/2026")

            errors = validate_balances(filtered)
            self.assertEqual(errors, [], f"Balance continuity errors in filtered output: {errors}")
        finally:
            os.unlink(path)

    def test_opening_balance(self):
        """Opening balance for range = balance just before first in-range txn."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            # Range 12/01 – 14/01. The txn before this range is 11/01 Groceries (bal=800).
            # So opening for range should be 800.
            filtered, summary = filter_by_date_range(rows, "12/01/2026", "14/01/2026")

            self.assertAlmostEqual(summary["opening_balance"], 800.0, places=2)
            # First txn in range (chronologically) is Salary +5000, so its balance = 800 + 5000 = 5800
            chrono = list(reversed(filtered))
            self.assertAlmostEqual(chrono[0]["balance"], 5800.0, places=2)
        finally:
            os.unlink(path)


class TestFilterSummary(unittest.TestCase):
    """Summary fields must be accurate."""

    def test_summary_totals(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            # Full range
            filtered, summary = filter_by_date_range(rows, "10/01/2026", "14/01/2026")

            # Total credits = 1000 (deposit) + 5000 (salary) = 6000
            self.assertAlmostEqual(summary["total_credits"], 6000.0, places=2)
            # Total debits = 200 + 2000 + 50 = 2250
            self.assertAlmostEqual(summary["total_debits"], 2250.0, places=2)
            self.assertAlmostEqual(summary["net_movement"], 3750.0, places=2)
            self.assertAlmostEqual(summary["closing_balance"], 3750.0, places=2)
        finally:
            os.unlink(path)


class TestFilterNoMatch(unittest.TestCase):
    """Date range with no matching transactions returns empty."""

    def test_no_match(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            filtered, summary = filter_by_date_range(rows, "01/06/2026", "30/06/2026")

            self.assertEqual(len(filtered), 0)
            self.assertEqual(summary["transaction_count"], 0)
        finally:
            os.unlink(path)


class TestFilterAfterInjection(unittest.TestCase):
    """Inject transactions, then filter — balances must reflect injections."""

    def test_inject_then_filter(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)

            # Inject a 500 credit on 11/01
            new_txns = [{
                "date": "11/01/2026", "description": "BONUS",
                "credit": 500.0, "debit": 0.0, "position": "top_of_date",
            }]
            updated = insert_and_recalculate(rows, new_txns)

            # Filter to 12/01 – 14/01
            filtered, summary = filter_by_date_range(updated, "12/01/2026", "14/01/2026")

            # Opening should be 800 (Groceries) + 500 (BONUS) = 1300
            self.assertAlmostEqual(summary["opening_balance"], 1300.0, places=2)

            # Salary balance should be 1300 + 5000 = 6300
            chrono = list(reversed(filtered))
            self.assertAlmostEqual(chrono[0]["balance"], 6300.0, places=2)

            # Closing = 6300 - 2000 - 50 = 4250
            self.assertAlmostEqual(summary["closing_balance"], 4250.0, places=2)

            errors = validate_balances(filtered)
            self.assertEqual(errors, [])
        finally:
            os.unlink(path)


class TestFilterRoundTrip(unittest.TestCase):
    """Filter → write → parse → validate balances."""

    def test_filter_write_reparse(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            input_path = f.name

        output_path = input_path + ".filtered.csv"

        try:
            rows = parse_csv(input_path)
            filtered, _ = filter_by_date_range(rows, "11/01/2026", "13/01/2026")
            write_csv(filtered, output_path)

            reparsed = parse_csv(output_path)
            self.assertEqual(len(reparsed), len(filtered))

            errors = validate_balances(reparsed)
            self.assertEqual(errors, [])
        finally:
            os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)


class TestFilterInvalidRange(unittest.TestCase):
    """from_date > to_date should raise ValueError."""

    def test_invalid_range(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            _make_csv(_simple_statement(), f.name)
            path = f.name

        try:
            rows = parse_csv(path)
            with self.assertRaises(ValueError):
                filter_by_date_range(rows, "14/01/2026", "10/01/2026")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
