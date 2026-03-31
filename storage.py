"""
Storage abstraction for the hierarchical multi-bank, multi-account architecture.

Directory structure:
    banks/{bank_id}/template.json, profile.json, template_images/
    data/{bank_id}/{account_slug}/account_data.json, transactions.csv, statements/

This module provides all filesystem operations and naming conventions.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
BANKS_DIR = BASE_DIR / "banks"
LEGACY_MAP_FILE = DATA_DIR / "_legacy_map.json"

HONORIFICS = {"mr", "mrs", "ms", "dr", "shri", "smt", "sri", "miss", "master"}


# ── Slugify ───────────────────────────────────────────────────────────────────

def slugify(customer_name: str, account_number: str = "") -> str:
    """Convert customer name to a filesystem-safe slug.

    'MRS VARSHITHA N' → 'varshitha_n'
    'MR HARSHA REDDYK' → 'harsha_reddyk'
    """
    if not customer_name:
        return "unnamed"

    words = customer_name.strip().lower().split()
    words = [w for w in words if w not in HONORIFICS]
    slug = "_".join(words)
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")

    if not slug:
        # Fallback to account number suffix
        if account_number:
            slug = "account_" + re.sub(r"[^0-9]", "", account_number)[-6:]
        else:
            slug = "unnamed"

    return slug


def unique_slug(bank_id: str, base_slug: str) -> str:
    """Ensure slug is unique under the bank. Appends _2, _3, etc. if needed."""
    bank_data_dir = DATA_DIR / bank_id
    if not bank_data_dir.exists():
        return base_slug

    slug = base_slug
    counter = 2
    while (bank_data_dir / slug).exists():
        slug = f"{base_slug}_{counter}"
        counter += 1

    return slug


# ── Path helpers ──────────────────────────────────────────────────────────────

def get_bank_template_dir(bank_id: str) -> Path:
    """Returns banks/{bank_id}/"""
    return BANKS_DIR / bank_id


def get_account_dir(bank_id: str, account_slug: str, create: bool = False) -> Path:
    """Returns data/{bank_id}/{account_slug}/ — creates if requested."""
    d = DATA_DIR / bank_id / account_slug
    if create:
        d.mkdir(parents=True, exist_ok=True)
        (d / "statements").mkdir(exist_ok=True)
    return d


def get_template_path(bank_id: str) -> Path:
    """Returns the template.json path for a bank."""
    return BANKS_DIR / bank_id / "template.json"


def get_account_data_path(bank_id: str, account_slug: str) -> Path:
    return DATA_DIR / bank_id / account_slug / "account_data.json"


def get_transactions_path(bank_id: str, account_slug: str) -> Path:
    return DATA_DIR / bank_id / account_slug / "transactions.csv"


def get_statements_dir(bank_id: str, account_slug: str) -> Path:
    d = DATA_DIR / bank_id / account_slug / "statements"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Statement naming ──────────────────────────────────────────────────────────

def statement_filename(start_date: str, end_date: str) -> str:
    """Generate a meaningful PDF filename from date range.

    '01/01/2026', '31/03/2026' → 'statement_2026-01-01_to_2026-03-31.pdf'
    """
    def parse(d):
        for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
            try:
                return datetime.strptime(d.strip(), fmt)
            except ValueError:
                continue
        return None

    s = parse(start_date)
    e = parse(end_date)

    if s and e:
        return f"statement_{s.strftime('%Y-%m-%d')}_to_{e.strftime('%Y-%m-%d')}.pdf"

    # Fallback
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"statement_{ts}.pdf"


# ── Listing ───────────────────────────────────────────────────────────────────

def list_accounts(bank_id: str) -> list:
    """List all accounts under a bank with metadata."""
    bank_data_dir = DATA_DIR / bank_id
    if not bank_data_dir.exists():
        return []

    accounts = []
    for d in sorted(bank_data_dir.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue

        account = {"slug": d.name, "bank_id": bank_id}

        # Read account data
        acct_file = d / "account_data.json"
        if acct_file.exists():
            try:
                with open(acct_file) as f:
                    data = json.load(f)
                account["customer_name"] = data.get("customer_name", "")
                account["account_number"] = data.get("account_number", "")
                account["account_type"] = data.get("account_type", "")
            except Exception:
                account["customer_name"] = d.name

        # Count transactions
        csv_file = d / "transactions.csv"
        if csv_file.exists():
            try:
                with open(csv_file) as f:
                    account["txn_count"] = max(0, sum(1 for _ in f) - 1)  # minus header
            except Exception:
                account["txn_count"] = 0
        else:
            account["txn_count"] = 0

        # Count statements
        stmts_dir = d / "statements"
        if stmts_dir.exists():
            pdfs = list(stmts_dir.glob("*.pdf"))
            account["statement_count"] = len(pdfs)
            if pdfs:
                latest = max(pdfs, key=lambda p: p.stat().st_mtime)
                account["last_generated"] = datetime.fromtimestamp(
                    latest.stat().st_mtime
                ).isoformat()
            else:
                account["last_generated"] = None
        else:
            account["statement_count"] = 0
            account["last_generated"] = None

        # Readiness
        account["has_account_data"] = acct_file.exists()
        account["has_transactions"] = csv_file.exists()

        accounts.append(account)

    return accounts


def list_statements(bank_id: str, account_slug: str) -> list:
    """List all generated PDFs for an account."""
    stmts_dir = DATA_DIR / bank_id / account_slug / "statements"
    if not stmts_dir.exists():
        return []

    statements = []
    for f in sorted(stmts_dir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True):
        statements.append({
            "filename": f.name,
            "size": f.stat().st_size,
            "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })

    return statements


def list_all_banks_with_accounts() -> list:
    """Dashboard data: all banks with their accounts."""
    banks_file = BANKS_DIR / "banks.json"
    if not banks_file.exists():
        return []

    with open(banks_file) as f:
        banks = json.load(f)

    result = []
    for bank in banks:
        bank_id = bank["id"]
        accounts = list_accounts(bank_id)
        result.append({
            "id": bank_id,
            "name": bank["name"],
            "full_name": bank.get("full_name", bank["name"]),
            "account_count": len(accounts),
            "accounts": accounts,
        })

    return result


# ── Legacy job resolution ─────────────────────────────────────────────────────

def load_legacy_map() -> dict:
    """Load the old job_id → (bank_id, account_slug) mapping."""
    if LEGACY_MAP_FILE.exists():
        with open(LEGACY_MAP_FILE) as f:
            return json.load(f)
    return {}


def save_legacy_map(mapping: dict):
    """Save the legacy map."""
    DATA_DIR.mkdir(exist_ok=True)
    with open(LEGACY_MAP_FILE, "w") as f:
        json.dump(mapping, f, indent=2)


def resolve_legacy_job(job_id: str):
    """Look up old job_id, return (bank_id, account_slug) or None."""
    mapping = load_legacy_map()
    entry = mapping.get(job_id)
    if entry:
        return entry["bank_id"], entry["account_slug"]

    # Check if old flat directory still exists
    old_dir = DATA_DIR / job_id
    if old_dir.is_dir() and (old_dir / "template.json").exists():
        return None  # exists but not migrated

    return None
