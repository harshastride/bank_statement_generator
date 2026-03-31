#!/usr/bin/env python3
"""
CLI entry point for the bank statement transaction injection engine.

Usage:
    python -m bank_statement_engine.main \
        --input Bank_Statement.csv \
        --output Bank_Statement_Updated.csv \
        --transactions transactions.json

    # Or use built-in defaults from config.py:
    python -m bank_statement_engine.main --input Bank_Statement.csv --output updated.csv
"""

import argparse
import json
import sys

from .engine import (
    parse_csv,
    validate_balances,
    insert_and_recalculate,
    filter_by_date_range,
    write_csv,
    print_summary,
    print_range_summary,
)
from .config import DEFAULT_TRANSACTIONS


def main():
    parser = argparse.ArgumentParser(
        description="Bank Statement Transaction Injection & Balance Recalculation"
    )
    parser.add_argument("--input", "-i", required=True, help="Input CSV file path")
    parser.add_argument("--output", "-o", required=True, help="Output CSV file path")
    parser.add_argument(
        "--transactions", "-t",
        help="JSON file with transactions to inject (omit to skip injection)",
    )
    parser.add_argument(
        "--use-defaults", action="store_true",
        help="Use default transactions from config.py when --transactions is not given",
    )
    parser.add_argument(
        "--from-date", help="Start date for extraction (DD/MM/YYYY), inclusive",
    )
    parser.add_argument(
        "--to-date", help="End date for extraction (DD/MM/YYYY), inclusive",
    )
    parser.add_argument(
        "--validate-only", action="store_true",
        help="Only validate balances, don't inject or filter",
    )
    args = parser.parse_args()

    # Parse input
    print(f"Parsing {args.input}...")
    rows = parse_csv(args.input)
    print(f"Loaded {len(rows)} transactions")

    # Validate existing balances
    errors = validate_balances(rows)
    if errors:
        print(f"WARNING: {len(errors)} balance continuity issues in source CSV:")
        for idx, expected, actual in errors[:5]:
            print(f"  Row {idx}: expected {expected:.2f}, got {actual:.2f}")
    else:
        print("Source CSV balance validation: OK")

    if args.validate_only:
        sys.exit(0 if not errors else 1)

    # --- Phase 1: Transaction injection (optional) ---
    new_txns = None
    if args.transactions:
        with open(args.transactions) as f:
            new_txns = json.load(f)
        print(f"Loaded {len(new_txns)} transactions from {args.transactions}")
    elif args.use_defaults:
        new_txns = DEFAULT_TRANSACTIONS
        print(f"Using {len(new_txns)} default transactions from config.py")

    if new_txns:
        for t in new_txns:
            t.setdefault("debit", 0.0)
            t.setdefault("credit", 0.0)
            t.setdefault("position", "top_of_date")

        original_closing = rows[0]["balance"] if rows else 0.0
        rows = insert_and_recalculate(rows, new_txns)
        print(f"Injected transactions, now {len(rows)} rows")

    # --- Phase 2: Date range filter (optional) ---
    range_summary = None
    if args.from_date and args.to_date:
        rows, range_summary = filter_by_date_range(rows, args.from_date, args.to_date)
        print(f"Filtered to {len(rows)} rows for {args.from_date} – {args.to_date}")
    elif args.from_date or args.to_date:
        parser.error("Both --from-date and --to-date are required for date filtering")

    # --- Write output ---
    write_csv(rows, args.output)
    print(f"Written {len(rows)} rows to {args.output}")

    # --- Summaries ---
    print()
    if new_txns:
        print_summary(rows, new_txns, original_closing)
        if range_summary:
            print()
    if range_summary:
        print_range_summary(range_summary)


if __name__ == "__main__":
    main()
