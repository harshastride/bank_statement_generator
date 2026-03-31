"""
Core engine for bank statement transaction injection and running balance recalculation.

The statement CSV is sorted newest-first (descending date). The CSV's Balance column
is the SOURCE OF TRUTH for the opening balance.

Algorithm:
  1. Compute opening balance from the OLDEST row (bottom of CSV) — this never changes
  2. Reverse to chronological order, insert new transactions
  3. Recalculate ALL balances forward from the fixed opening balance
  4. Reverse back to newest-first

The opening balance is derived ONCE from the original data before any insertions.
"""

import csv
import copy
from datetime import datetime


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _parse_amount(val):
    """Parse a numeric string (possibly with commas/quotes) to float. Empty → 0.0."""
    if not val:
        return 0.0
    cleaned = str(val).replace('"', '').replace(',', '').strip()
    if not cleaned:
        return 0.0
    return round(float(cleaned), 2)


def _parse_date(date_str):
    """Parse DD/MM/YY or DD/MM/YYYY to datetime."""
    date_str = date_str.strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {date_str!r}")


# ---------------------------------------------------------------------------
# Parse CSV
# ---------------------------------------------------------------------------

def parse_csv(filepath):
    """
    Parse a bank statement CSV into a list of row dicts.

    Returns rows in original file order (newest-first).
    Each row: {date_str, description, credit, debit, balance, _date}
    where credit/debit/balance are floats and _date is a datetime.

    Auto-fixes rows where Credit/Debit are in the wrong column by checking
    balance continuity.
    """
    rows = []
    with open(filepath, "r", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            date_str = raw.get("Date", "").strip()
            if not date_str:
                continue
            rows.append({
                "date_str": date_str,
                "description": raw.get("Description", "").strip(),
                "credit": _parse_amount(raw.get("Credit", "")),
                "debit": _parse_amount(raw.get("Debit", "")),
                "balance": _parse_amount(raw.get("Balance", "")),
                "_date": _parse_date(date_str),
            })
    _auto_fix_credit_debit(rows)
    return rows


def _auto_fix_credit_debit(rows):
    """Fix rows where Credit/Debit are in the wrong column.

    Walks chronologically and checks each row's balance against the previous.
    If credit-debit doesn't match the balance change but swapping them does,
    the values are swapped.
    """
    if len(rows) < 2:
        return

    chrono = list(reversed(rows))
    fixed_count = 0

    for i in range(1, len(chrono)):
        prev_bal = chrono[i - 1]["balance"]
        cur = chrono[i]
        expected = round(prev_bal + cur["credit"] - cur["debit"], 2)
        actual = cur["balance"]

        if abs(expected - actual) <= 0.02:
            continue

        swapped = round(prev_bal + cur["debit"] - cur["credit"], 2)
        if abs(swapped - actual) <= 0.02:
            cur["credit"], cur["debit"] = cur["debit"], cur["credit"]
            fixed_count += 1

    if fixed_count:
        print(f"Auto-fixed credit/debit swap in {fixed_count} rows")


def validate_balances(rows, tolerance=0.02):
    """
    Validate running balance continuity on a newest-first row list.

    For each row i (0 = newest):
        balance[i] should equal balance[i+1] + credit[i] - debit[i]

    Returns list of (index, expected, actual) for mismatches.
    """
    errors = []
    for i in range(len(rows) - 1):
        expected = round(rows[i + 1]["balance"] + rows[i]["credit"] - rows[i]["debit"], 2)
        actual = rows[i]["balance"]
        if abs(expected - actual) > tolerance:
            errors.append((i, expected, actual))
    return errors


# ---------------------------------------------------------------------------
# Opening balance
# ---------------------------------------------------------------------------

def _compute_opening_balance(rows_chrono):
    """Compute the balance before the first chronological transaction.

    Uses the OLDEST row (first in chronological order = last in CSV).
    opening = oldest_balance - oldest_credit + oldest_debit
    """
    first = rows_chrono[0]
    return round(first["balance"] - first["credit"] + first["debit"], 2)


# ---------------------------------------------------------------------------
# Insert & Recalculate
# ---------------------------------------------------------------------------

def insert_and_recalculate(rows, new_txns):
    """
    Insert new transactions and recalculate balances.

    Uses delta-shift: the CSV's existing balances are preserved for rows before
    the earliest insertion. Only rows from the insertion date onward are shifted
    by the net amount of the injected transaction. This avoids recomputing from
    scratch, which would break on CSVs with missing transaction rows (gaps).

    For each new transaction:
      1. Insert BEFORE same-date rows in chronological order so that ALL rows
         on the insertion date (and after) get the balance shift.
      2. Set its balance = previous_row_balance + credit - debit
      3. Shift every row from the insertion point onward by +credit -debit

    Args:
        rows: list of row dicts from parse_csv (newest-first order)
        new_txns: list of dicts with date, description, credit, debit, position

    Returns:
        Updated list of rows (newest-first) with correct balances.
    """
    rows = copy.deepcopy(rows)

    if not rows and not new_txns:
        return rows

    # Work in chronological order (oldest-first)
    rows_chrono = list(reversed(rows))

    for nt in new_txns:
        date_str = nt["date"]
        nt_date = _parse_date(date_str)
        credit = round(float(nt.get("credit", 0) or 0), 2)
        debit = round(float(nt.get("debit", 0) or 0), 2)
        delta = round(credit - debit, 2)

        new_row = {
            "date_str": date_str,
            "description": nt["description"],
            "credit": credit,
            "debit": debit,
            "balance": 0.0,  # set below
            "_date": nt_date,
            "_injected": True,
        }

        # Idempotency: skip if an identical transaction already exists
        if _transaction_exists(rows_chrono, new_row):
            continue

        # Insert BEFORE same-date rows in chronological order.
        # This ensures ALL rows on the same date (and after) get the shift.
        insert_idx = _find_insert_index(rows_chrono, nt_date)

        # Compute this row's balance from the row just before it
        if insert_idx > 0:
            prev_balance = rows_chrono[insert_idx - 1]["balance"]
        else:
            # Inserting before all existing rows
            if rows_chrono:
                prev_balance = _compute_opening_balance(rows_chrono)
            else:
                prev_balance = 0.0

        new_row["balance"] = round(prev_balance + delta, 2)

        # Insert the new row
        rows_chrono.insert(insert_idx, new_row)

        # Shift ALL rows after the insertion by the delta
        for i in range(insert_idx + 1, len(rows_chrono)):
            rows_chrono[i]["balance"] = round(rows_chrono[i]["balance"] + delta, 2)

    # Reverse back to newest-first
    result = list(reversed(rows_chrono))

    # Warn about negative balances
    negatives = [r for r in rows_chrono if r["balance"] < 0]
    if negatives:
        print(f"WARNING: {len(negatives)} rows have negative balances")
        for r in negatives[:5]:
            print(f"  {r['date_str']} balance={r['balance']:.2f}")

    return result


def _find_insert_index(rows_chrono, target_date):
    """
    Find insertion index in chronological (oldest-first) list.

    Inserts BEFORE the first row with date >= target_date.
    This means the new transaction is the first event of that date,
    so all same-date rows (and later) get the balance shift.

    In the newest-first output, the injected row appears at the BOTTOM
    of its date group (oldest event of the day).
    """
    for i, row in enumerate(rows_chrono):
        if row["_date"] >= target_date:
            return i
    return len(rows_chrono)


def _transaction_exists(rows, new_row):
    """Check if an identical transaction already exists (for idempotency)."""
    for r in rows:
        if (r["date_str"] == new_row["date_str"]
                and r["description"] == new_row["description"]
                and r["credit"] == new_row["credit"]
                and r["debit"] == new_row["debit"]):
            return True
    return False


# ---------------------------------------------------------------------------
# Write CSV
# ---------------------------------------------------------------------------

def write_csv(rows, output_path):
    """
    Write rows to CSV in newest-first order.

    Credit/Debit: number if > 0, empty string if 0.
    Balance: 2 decimal places, no commas.
    """
    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", "Description", "Credit", "Debit", "Balance"])
        for row in rows:
            credit = f"{row['credit']:.2f}" if row["credit"] > 0 else ""
            debit = f"{row['debit']:.2f}" if row["debit"] > 0 else ""
            balance = f"{row['balance']:.2f}"
            writer.writerow([row["date_str"], row["description"], credit, debit, balance])


# ---------------------------------------------------------------------------
# Summary Report
# ---------------------------------------------------------------------------

def print_summary(rows, new_txns, original_closing):
    """Print the injection summary report."""
    if not rows:
        print("No rows to report.")
        return

    rows_chrono = list(reversed(rows))
    oldest = rows_chrono[0]
    opening = round(oldest["balance"] - oldest["credit"] + oldest["debit"], 2)
    closing = rows[0]["balance"]  # newest row = closing balance

    print("=" * 50)
    print("TRANSACTION INJECTION SUMMARY")
    print("=" * 50)
    print(f"Opening Balance: {_fmt_inr(opening)}")
    print(f"Closing Balance: {_fmt_inr(closing)} (was {_fmt_inr(original_closing)})")
    print()

    # Inserted transactions
    injected = [r for r in rows_chrono if r.get("_injected")]
    if injected:
        print("Transactions Inserted:")
        for i, r in enumerate(injected, 1):
            amt = r["credit"] - r["debit"]
            sign = "+" if amt >= 0 else ""
            print(f"  {i}. {r['date_str']} | {r['description']} | "
                  f"{sign}{_fmt_inr(abs(amt))} | New Balance: {_fmt_inr(r['balance'])}")
        print()

    # Balance impact
    total_credits = sum(r["credit"] for r in injected)
    total_debits = sum(r["debit"] for r in injected)
    delta = round(closing - original_closing, 2)
    print("Balance Impact:")
    if total_credits > 0:
        print(f"  Total credits added: {_fmt_inr(total_credits)}")
    if total_debits > 0:
        print(f"  Total debits added: {_fmt_inr(total_debits)}")
    print(f"  Closing balance delta: +{_fmt_inr(delta)}" if delta >= 0
          else f"  Closing balance delta: -{_fmt_inr(abs(delta))}")
    print()

    # Negative balance check
    negatives = [r for r in rows_chrono if r["balance"] < 0]
    print("Negative Balance Check:")
    if not negatives:
        print("  No negative balances found")
    else:
        print(f"  {len(negatives)} rows still have negative balances")
        for r in negatives[:10]:
            print(f"    {r['date_str']}: {_fmt_inr(r['balance'])}")
    print()

    # Validation
    errors = validate_balances(rows)
    print("Validation:")
    if not errors:
        print(f"  Running balance verified for all {len(rows)} rows")
    else:
        print(f"  {len(errors)} balance continuity errors found!")
    print("=" * 50)


def _fmt_inr(amount):
    """Format amount in Indian style with rupee symbol."""
    return f"\u20b9{amount:,.2f}"


# ---------------------------------------------------------------------------
# Date Range Filtering
# ---------------------------------------------------------------------------

def filter_by_date_range(rows, from_date_str, to_date_str):
    """
    Extract transactions within a date range and return a self-contained statement.

    Uses the CSV's own Balance column (source of truth). The opening balance for
    the range = the balance of the last transaction BEFORE the range starts.

    Args:
        rows: newest-first list with correct balances (from parse_csv or insert_and_recalculate)
        from_date_str: start date inclusive (DD/MM/YYYY or DD/MM/YY)
        to_date_str: end date inclusive (DD/MM/YYYY or DD/MM/YY)

    Returns:
        (filtered_rows, summary_dict) where filtered_rows is newest-first and
        summary_dict has period info for reporting.
    """
    from_dt = _parse_date(from_date_str)
    to_dt = _parse_date(to_date_str)

    if from_dt > to_dt:
        raise ValueError(f"from_date ({from_date_str}) is after to_date ({to_date_str})")

    # Work in chronological order (oldest-first)
    rows_chrono = list(reversed(rows))

    if not rows_chrono:
        return [], _empty_range_summary(from_date_str, to_date_str)

    # Walk chronologically, using the CSV's own balances
    opening_for_range = _compute_opening_balance(rows_chrono)  # default: before first txn
    filtered_chrono = []

    for row in rows_chrono:
        if row["_date"] < from_dt:
            # Last balance before the range = opening for the range
            opening_for_range = row["balance"]
        elif row["_date"] <= to_dt:
            filtered_chrono.append(row)
        # rows after to_dt are skipped

    filtered_newest_first = list(reversed(filtered_chrono))

    # Build summary
    if filtered_chrono:
        total_credits = round(sum(r["credit"] for r in filtered_chrono), 2)
        total_debits = round(sum(r["debit"] for r in filtered_chrono), 2)
        closing = filtered_chrono[-1]["balance"]
    else:
        total_credits = 0.0
        total_debits = 0.0
        closing = opening_for_range

    summary = {
        "from_date": from_date_str,
        "to_date": to_date_str,
        "opening_balance": opening_for_range,
        "closing_balance": closing,
        "total_credits": total_credits,
        "total_debits": total_debits,
        "net_movement": round(total_credits - total_debits, 2),
        "transaction_count": len(filtered_chrono),
    }

    return filtered_newest_first, summary


def _empty_range_summary(from_date_str, to_date_str):
    return {
        "from_date": from_date_str,
        "to_date": to_date_str,
        "opening_balance": 0.0,
        "closing_balance": 0.0,
        "total_credits": 0.0,
        "total_debits": 0.0,
        "net_movement": 0.0,
        "transaction_count": 0,
    }


def print_range_summary(summary):
    """Print the date range extraction summary."""
    print("=" * 50)
    print("DATE RANGE EXTRACTION SUMMARY")
    print("=" * 50)
    print(f"Period: {summary['from_date']} to {summary['to_date']}")
    print(f"Transactions: {summary['transaction_count']}")
    print()
    print(f"Opening Balance:  {_fmt_inr(summary['opening_balance'])}")
    print(f"Total Credits:   +{_fmt_inr(summary['total_credits'])}")
    print(f"Total Debits:    -{_fmt_inr(summary['total_debits'])}")
    print(f"Net Movement:     {'+' if summary['net_movement'] >= 0 else ''}{_fmt_inr(summary['net_movement'])}")
    print(f"Closing Balance:  {_fmt_inr(summary['closing_balance'])}")
    print("=" * 50)
