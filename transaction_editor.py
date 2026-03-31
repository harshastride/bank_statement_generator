"""
Transaction Editor — Add/modify transactions and auto-recalculate all balances.

Delegates to bank_statement_engine for core logic. This module provides the
same API surface used by app.py and CLI.

Usage:
    # CLI
    python transaction_editor.py transactions.csv --add 27/03/26 "TRANSFER | UPI123 | John | U@123" --credit 500
    python transaction_editor.py transactions.csv --recalculate

    # As a module
    from transaction_editor import load_csv, add_transaction, recalculate_balances, save_csv
"""

import argparse
import csv
from datetime import datetime

from bank_statement_engine.engine import (
    parse_csv as _engine_parse,
    insert_and_recalculate,
    validate_balances,
    _parse_amount,
    _parse_date,
)


def load_csv(csv_path):
    """Load transactions from CSV. Returns list of dicts with: date, description, credit, debit, balance.

    Auto-fixes rows where Credit/Debit are in the wrong column by checking
    balance continuity.
    """
    transactions = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            txn = {
                "date": row.get("Date", "").strip(),
                "description": row.get("Description", "").strip(),
                "credit": row.get("Credit", "").strip().replace('"', '').replace(',', ''),
                "debit": row.get("Debit", "").strip().replace('"', '').replace(',', ''),
                "balance": row.get("Balance", "").strip().replace('"', '').replace(',', ''),
            }
            if txn["date"]:
                transactions.append(txn)
    _auto_fix_credit_debit(transactions)
    return transactions


def _auto_fix_credit_debit(transactions):
    """Fix rows where Credit/Debit are in the wrong column.

    Walks chronologically and checks each row's balance against the previous.
    If credit-debit doesn't match the balance change but swapping them does,
    the values are swapped.
    """
    if len(transactions) < 2:
        return

    chrono = list(reversed(transactions))
    fixed_count = 0

    for i in range(1, len(chrono)):
        prev_bal = _parse_amount(chrono[i - 1]["balance"])
        cur = chrono[i]
        credit = _parse_amount(cur.get("credit", ""))
        debit = _parse_amount(cur.get("debit", ""))
        actual_bal = _parse_amount(cur["balance"])

        expected = round(prev_bal + credit - debit, 2)
        if abs(expected - actual_bal) <= 0.02:
            continue

        swapped = round(prev_bal + debit - credit, 2)
        if abs(swapped - actual_bal) <= 0.02:
            cur["credit"], cur["debit"] = cur["debit"], cur["credit"]
            fixed_count += 1

    if fixed_count:
        print(f"Auto-fixed credit/debit swap in {fixed_count} rows")


def _to_engine_rows(transactions):
    """Convert legacy format (string amounts) to engine format (float amounts)."""
    rows = []
    for t in transactions:
        credit = _parse_amount(t["credit"])
        debit = _parse_amount(t["debit"])
        balance = _parse_amount(t["balance"])
        rows.append({
            "date_str": t["date"],
            "description": t["description"],
            "credit": credit,
            "debit": debit,
            "balance": balance,
            "_date": _parse_date(t["date"]),
        })
    return rows


def _from_engine_rows(rows):
    """Convert engine format back to legacy format (string amounts)."""
    transactions = []
    for r in rows:
        transactions.append({
            "date": r["date_str"],
            "description": r["description"],
            "credit": f"{r['credit']:,.2f}" if r["credit"] > 0 else "",
            "debit": f"{r['debit']:,.2f}" if r["debit"] > 0 else "",
            "balance": f"{r['balance']:,.2f}",
        })
    return transactions


def recalculate_balances(transactions, starting_balance=None):
    """Recalculate all balances by running the full engine recalculation."""
    if not transactions:
        return transactions

    engine_rows = _to_engine_rows(transactions)
    # Use insert_and_recalculate with no new transactions — just recalculates
    recalculated = insert_and_recalculate(engine_rows, [])
    legacy = _from_engine_rows(recalculated)

    # Update in place
    for i, t in enumerate(transactions):
        t["balance"] = legacy[i]["balance"]
        t["credit"] = legacy[i]["credit"]
        t["debit"] = legacy[i]["debit"]

    return transactions


def add_transaction(transactions, date, description, credit=None, debit=None):
    """Add a new transaction and recalculate all balances."""
    engine_rows = _to_engine_rows(transactions)
    new_txns = [{
        "date": date,
        "description": description,
        "credit": float(credit) if credit else 0.0,
        "debit": float(debit) if debit else 0.0,
        "position": "top_of_date",
    }]
    updated = insert_and_recalculate(engine_rows, new_txns)
    result = _from_engine_rows(updated)

    transactions.clear()
    transactions.extend(result)
    return transactions


def add_transactions_bulk(transactions, new_txns):
    """Add multiple transactions at once and recalculate."""
    engine_rows = _to_engine_rows(transactions)
    engine_new = []
    for nt in new_txns:
        engine_new.append({
            "date": nt["date"],
            "description": nt["description"],
            "credit": float(nt.get("credit") or 0),
            "debit": float(nt.get("debit") or 0),
            "position": nt.get("position", "top_of_date"),
        })
    updated = insert_and_recalculate(engine_rows, engine_new)
    result = _from_engine_rows(updated)

    transactions.clear()
    transactions.extend(result)
    return transactions


def save_csv(transactions, csv_path):
    """Save transactions to CSV."""
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Date", "Description", "Credit", "Debit", "Balance"])
        writer.writeheader()
        for txn in transactions:
            writer.writerow({
                "Date": txn["date"],
                "Description": txn["description"],
                "Credit": txn["credit"],
                "Debit": txn["debit"],
                "Balance": txn["balance"],
            })
    print(f"Saved {len(transactions)} transactions → {csv_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Transaction Editor")
    parser.add_argument("csv", help="Input CSV file")
    parser.add_argument("--add", nargs=2, metavar=("DATE", "DESC"),
                        help="Add transaction: DATE (DD/MM/YY) DESCRIPTION")
    parser.add_argument("--credit", type=float, help="Credit amount")
    parser.add_argument("--debit", type=float, help="Debit amount")
    parser.add_argument("--recalculate", action="store_true",
                        help="Just recalculate all balances")
    parser.add_argument("--output", "-o", help="Output CSV (default: overwrite input)")
    args = parser.parse_args()

    txns = load_csv(args.csv)
    print(f"Loaded {len(txns)} transactions")

    if args.add:
        date, desc = args.add
        add_transaction(txns, date, desc, credit=args.credit, debit=args.debit)
        print(f"Added transaction on {date}")
    elif args.recalculate:
        recalculate_balances(txns)
        print("Recalculated all balances")

    output = args.output or args.csv
    save_csv(txns, output)
