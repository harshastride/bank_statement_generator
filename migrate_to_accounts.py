"""
Migration script: Move flat job directories into the hierarchical
bank > account > statements structure.

Usage:
    python migrate_to_accounts.py              # dry run (preview only)
    python migrate_to_accounts.py --execute    # actually migrate

This script:
1. Scans data/ for flat job directories (8-char UUIDs with account_data.json)
2. Reads customer_name to generate account slugs
3. Copies files into data/{bank_id}/{slug}/
4. Saves _legacy_map.json for backward compatibility
5. Does NOT delete old directories
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

from storage import DATA_DIR, BANKS_DIR, slugify, unique_slug, save_legacy_map


def is_flat_job(d: Path) -> bool:
    """Check if a directory is an old flat job (8-char UUID with data files)."""
    if not d.is_dir():
        return False
    if d.name.startswith("_"):
        return False
    # Must look like a UUID prefix (hex chars, 8 chars)
    if not re.match(r'^[0-9a-f]{8}$', d.name):
        return False
    # Must have at least account_data.json or transactions.csv
    return (d / "account_data.json").exists() or (d / "transactions.csv").exists()


def detect_bank_id(job_dir: Path) -> str:
    """Try to determine which bank a job belongs to.

    Compares the job's template against bank templates.
    Falls back to 'hsbc' since that's the only bank currently.
    """
    template_path = job_dir / "template.json"
    if not template_path.exists():
        return "hsbc"

    try:
        with open(template_path) as f:
            job_tmpl = json.load(f)

        # Check if profile exists and has identifying info
        profile = job_tmpl.get("profile", {})
        # For now, check if any bank's template matches by page dimensions
        for bank_dir in BANKS_DIR.iterdir():
            if not bank_dir.is_dir() or bank_dir.name == "banks.json":
                continue
            bank_tmpl_path = bank_dir / "template.json"
            if bank_tmpl_path.exists():
                with open(bank_tmpl_path) as f:
                    bank_tmpl = json.load(f)
                if (job_tmpl.get("page_width") == bank_tmpl.get("page_width") and
                    job_tmpl.get("page_height") == bank_tmpl.get("page_height")):
                    return bank_dir.name
    except Exception:
        pass

    return "hsbc"


def migrate(execute: bool = False):
    """Scan flat jobs and migrate to hierarchical structure."""
    print(f"Scanning {DATA_DIR} for flat job directories...")

    flat_jobs = []
    for d in sorted(DATA_DIR.iterdir()):
        if is_flat_job(d):
            flat_jobs.append(d)

    print(f"Found {len(flat_jobs)} flat jobs to migrate")

    if not flat_jobs:
        print("Nothing to migrate.")
        return

    legacy_map = {}
    migrated = 0
    skipped = 0

    for job_dir in flat_jobs:
        job_id = job_dir.name

        # Skip already-migrated jobs
        if (job_dir / "._migrated").exists():
            skipped += 1
            continue

        # Read account data
        account_data = {}
        acct_file = job_dir / "account_data.json"
        if acct_file.exists():
            try:
                with open(acct_file) as f:
                    account_data = json.load(f)
            except Exception:
                pass

        customer_name = account_data.get("customer_name", "")
        account_number = account_data.get("account_number", "")
        bank_id = detect_bank_id(job_dir)

        # Generate slug
        base_slug = slugify(customer_name, account_number)
        slug = unique_slug(bank_id, base_slug) if execute else base_slug

        dest_dir = DATA_DIR / bank_id / slug

        print(f"  {job_id} → {bank_id}/{slug}")
        print(f"    Customer: {customer_name}")
        print(f"    Account:  {account_number}")

        if execute:
            dest_dir.mkdir(parents=True, exist_ok=True)
            (dest_dir / "statements").mkdir(exist_ok=True)

            # Copy account_data.json
            if acct_file.exists():
                shutil.copy2(str(acct_file), str(dest_dir / "account_data.json"))

            # Copy transactions.csv
            txn_file = job_dir / "transactions.csv"
            if txn_file.exists():
                shutil.copy2(str(txn_file), str(dest_dir / "transactions.csv"))

            # Copy output.pdf to statements/
            output_file = job_dir / "output.pdf"
            if output_file.exists():
                # Name it with modification time
                from datetime import datetime
                mtime = datetime.fromtimestamp(output_file.stat().st_mtime)
                stmt_name = f"statement_{mtime.strftime('%Y-%m-%d_%H%M%S')}.pdf"
                shutil.copy2(str(output_file), str(dest_dir / "statements" / stmt_name))

            # Mark as migrated (don't delete)
            (job_dir / "._migrated").touch()

            legacy_map[job_id] = {"bank_id": bank_id, "account_slug": slug}
            migrated += 1
        else:
            migrated += 1

    if execute and legacy_map:
        # Merge with existing map
        existing = {}
        try:
            from storage import load_legacy_map
            existing = load_legacy_map()
        except Exception:
            pass
        existing.update(legacy_map)
        save_legacy_map(existing)
        print(f"\nSaved legacy map: {len(existing)} entries → {DATA_DIR / '_legacy_map.json'}")

    print(f"\n{'Migrated' if execute else 'Would migrate'}: {migrated}")
    print(f"Skipped (already migrated): {skipped}")

    if not execute:
        print(f"\nThis was a DRY RUN. To actually migrate, run:")
        print(f"  python migrate_to_accounts.py --execute")


if __name__ == "__main__":
    execute = "--execute" in sys.argv
    migrate(execute=execute)
