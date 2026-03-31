"""
FastAPI backend for the PDF Statement Generator service.

Architecture: Banks > Accounts > Statements
  banks/{bank_id}/  — template, profile, images (shared per bank)
  data/{bank_id}/{account_slug}/  — account data, transactions, statements

New API (hierarchical):
  GET  /api/dashboard                                    → all banks + accounts
  POST /api/banks/{bank_id}/accounts                     → create account
  GET  /api/banks/{bank_id}/accounts                     → list accounts
  GET  /api/banks/{bank_id}/accounts/{slug}/data         → get account data
  PUT  /api/banks/{bank_id}/accounts/{slug}/data         → save account data
  POST /api/banks/{bank_id}/accounts/{slug}/transactions → upload CSV
  GET  /api/banks/{bank_id}/accounts/{slug}/transactions → get transactions
  POST /api/banks/{bank_id}/accounts/{slug}/transactions/save
  POST /api/banks/{bank_id}/accounts/{slug}/transactions/recalculate
  POST /api/banks/{bank_id}/accounts/{slug}/generate-range
  GET  /api/banks/{bank_id}/accounts/{slug}/statements
  GET  /api/banks/{bank_id}/accounts/{slug}/statements/{filename}

Legacy API (kept for chrome extension + backward compat):
  POST /api/jobs/{id}/generate-range
  GET  /api/jobs/{id}/download
"""

import csv
import json
import os
import shutil
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from pdf_template_builder import (
    create_template,
    generate_pdf as generate_pdf_legacy,
    parse_transactions_csv,
    _extract_last_page_footer,
)
from universal_generator import generate_pdf as generate_pdf_universal
from html_renderer import generate_pdf_html, has_html_layout


def generate_pdf(template_path, account_path, csv_path, output_path, **kwargs):
    """Smart router: use legacy engine for HSBC (proven), universal for everything else."""
    import json as _json
    with open(template_path) as f:
        tmpl = _json.load(f)

    profile = tmpl.get("profile", {})

    # Use legacy engine if: no profile (old HSBC templates) OR profile has v1 keys (old format)
    # The legacy engine handles DEFAULT_HSBC_PROFILE fallback perfectly
    has_v2_table = "table" in profile
    has_v1_columns = "columns" in profile and "table" not in profile
    no_profile = not profile

    if no_profile or has_v1_columns:
        # HSBC / old format → use the battle-tested legacy engine
        return generate_pdf_legacy(template_path, account_path, csv_path, output_path, **kwargs)
    else:
        # New v2 profile → use universal engine
        return generate_pdf_universal(template_path, account_path, csv_path, output_path, **kwargs)
from transaction_editor import (
    load_csv as load_csv_editor,
    add_transactions_bulk,
    recalculate_balances,
    save_csv,
)
from storage import (
    DATA_DIR, BANKS_DIR,
    slugify, unique_slug,
    get_account_dir, get_template_path, get_account_data_path,
    get_transactions_path, get_statements_dir,
    statement_filename,
    list_accounts, list_statements, list_all_banks_with_accounts,
    resolve_legacy_job, load_legacy_map,
)

app = FastAPI(title="PDF Statement Generator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR.mkdir(exist_ok=True)


def _load_banks():
    banks_file = BANKS_DIR / "banks.json"
    if not banks_file.exists():
        return []
    with open(banks_file) as f:
        return json.load(f)


def _parse_date(date_str: str) -> datetime:
    date_str = date_str.strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {date_str}")


def _stamp_ist_timestamps(account_path: Path):
    """Update account_data.json with current IST date/time before PDF generation."""
    now_ist = datetime.now(IST)
    with open(account_path) as f:
        data = json.load(f)
    data["generated_on"] = now_ist.strftime("%d/%m/%Y %I:%M %p")
    data["download_date"] = now_ist.strftime("%d/%m/%Y")
    data["print_date"] = now_ist.strftime("%-m/%-d/%y")
    data["print_time"] = now_ist.strftime("%-I:%M %p")
    with open(account_path, "w") as f:
        json.dump(data, f, indent=2)


def _ensure_account(bank_id: str, slug: str) -> Path:
    d = get_account_dir(bank_id, slug)
    if not d.exists():
        raise HTTPException(404, f"Account {bank_id}/{slug} not found")
    return d


def _get_template_for_bank(bank_id: str) -> Path:
    """Get template path for a bank, with image_dir fixed to absolute path."""
    tp = get_template_path(bank_id)
    if not tp.exists():
        raise HTTPException(400, f"No template for bank: {bank_id}")
    return tp


def _prepare_template_for_generation(bank_id: str) -> str:
    """Read bank template, fix image_dir, write to temp file for generation."""
    tp = _get_template_for_bank(bank_id)
    with open(tp) as f:
        tmpl = json.load(f)

    # Fix image_dir to absolute path
    bank_dir = BANKS_DIR / bank_id
    tmpl["image_dir"] = str(bank_dir / "template_images")

    # Write to temp file (don't modify the bank's template.json)
    import tempfile
    tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir=str(DATA_DIR))
    json.dump(tmpl, tf, indent=2, default=str)
    tf.close()
    return tf.name


def _get_bank_csv_header_map(bank_id: str) -> dict:
    """Load the csvHeaderMap from a bank's fields.json."""
    fields_path = BANKS_DIR / bank_id / "fields.json"
    if not fields_path.exists():
        return {}
    with open(fields_path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data.get("csvHeaderMap", {})
    return {}


def _normalize_csv(content: bytes, bank_id: str) -> bytes:
    """Normalize bank-specific CSV headers to internal format before saving."""
    header_map = _get_bank_csv_header_map(bank_id)
    if not header_map:
        return content

    text = content.decode("utf-8-sig")
    lines = text.strip().split("\n")
    if not lines:
        return content

    # Map header columns to internal keys
    raw_headers = lines[0].strip().split(",")
    internal_keys = []
    for h in raw_headers:
        h_clean = h.strip().strip('"')
        mapped = header_map.get(h_clean, h_clean.lower().replace(" ", "_").replace(".", ""))
        internal_keys.append(mapped)

    # Map internal keys to standard CSV header names
    KEY_TO_HEADER = {
        "date": "Date", "description": "Description", "credit": "Credit",
        "debit": "Debit", "balance": "Balance", "ref": "Ref",
        "value_date": "Value_Date",
    }
    new_headers = [KEY_TO_HEADER.get(k, k.title()) for k in internal_keys]
    lines[0] = ",".join(new_headers)
    return "\n".join(lines).encode("utf-8")


ALL_CSV_FIELDS = ["Date", "Description", "Credit", "Debit", "Balance", "Ref", "Value_Date"]


def _write_csv(rows: list, path: str):
    # Determine which extra columns have data
    fieldnames = ["Date", "Description", "Credit", "Debit", "Balance"]
    has_ref = any(row.get("ref", "") for row in rows)
    has_vdate = any(row.get("value_date", "") for row in rows)
    if has_ref:
        fieldnames.insert(2, "Ref")
    if has_vdate:
        fieldnames.insert(fieldnames.index("Debit"), "Value_Date")

    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out = {
                "Date": row.get("date", ""),
                "Description": row.get("description", ""),
                "Credit": row.get("credit", ""),
                "Debit": row.get("debit", ""),
                "Balance": row.get("balance", ""),
            }
            if has_ref:
                out["Ref"] = row.get("ref", "")
            if has_vdate:
                out["Value_Date"] = row.get("value_date", "")
            writer.writerow(out)


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/dashboard")
def dashboard():
    """Get all banks with their accounts and statement counts."""
    return {"banks": list_all_banks_with_accounts()}


# ══════════════════════════════════════════════════════════════════════════════
# BANKS
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/banks")
def api_list_banks():
    banks = _load_banks()
    return {"banks": [{"id": b["id"], "name": b["name"], "full_name": b.get("full_name", b["name"])} for b in banks]}


@app.post("/api/banks/onboard")
async def onboard_bank(file: UploadFile = File(...), bank_name: str = "", bank_id: str = ""):
    """Onboard a new bank by uploading a sample statement PDF."""
    from layout_detector import detect_layout
    from pdf_analyzer import analyze_pdf as _analyze_pdf

    if not bank_id:
        bank_id = bank_name.lower().replace(" ", "_") if bank_name else str(uuid.uuid4())[:8]
    if not bank_name:
        bank_name = bank_id.upper()

    bank_dir = BANKS_DIR / bank_id
    bank_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = bank_dir / "source.pdf"
    content = await file.read()
    pdf_path.write_bytes(content)

    template_path = bank_dir / "template.json"
    image_dir = bank_dir / "template_images"

    try:
        create_template(str(pdf_path), str(template_path), str(image_dir))
    except Exception as e:
        shutil.rmtree(str(bank_dir), ignore_errors=True)
        raise HTTPException(500, f"Template extraction failed: {e}")

    with open(template_path) as f:
        tmpl = json.load(f)
    profile = tmpl.get("profile", {})

    banks = _load_banks()
    banks = [b for b in banks if b["id"] != bank_id]
    banks.append({
        "id": bank_id, "name": bank_name, "full_name": bank_name, "logo": bank_id,
        "sample_account": {"customer_name": "", "account_number": "", "account_type": "",
                           "current_balance": "0.00", "currency": "INR"},
    })
    with open(BANKS_DIR / "banks.json", "w") as f:
        json.dump(banks, f, indent=2)

    pdf_path.unlink(missing_ok=True)

    return {"status": "onboarded", "bank_id": bank_id, "bank_name": bank_name,
            "columns_detected": [c["name"] for c in profile.get("columns", [])]}


# ── New Bank Setup (Analyzer + Template Builder) ──────────────────────────

@app.post("/api/analyze-pdf")
async def analyze_pdf_endpoint(file: UploadFile = File(...)):
    from pdf_analyzer import analyze_pdf as _analyze_pdf

    setup_dir = DATA_DIR / "_bank_setup"
    setup_dir.mkdir(exist_ok=True)

    pdf_path = setup_dir / "source.pdf"
    content = await file.read()
    pdf_path.write_bytes(content)

    image_dir = setup_dir / "template_images"

    try:
        layout = _analyze_pdf(str(pdf_path), pages=[1, 2], image_dir=str(image_dir))
    except Exception as e:
        raise HTTPException(500, f"PDF analysis failed: {e}")

    for page in layout.get("pages", []):
        for img in page.get("images", []):
            img.pop("file", None)
        for vr in page.get("vector_regions", []):
            vr.pop("file", None)

    guide_path = Path(__file__).parent / "GUIDE_AI_PROFILE_EXTRACTION.md"
    prompt_text = ""
    if guide_path.exists():
        with open(guide_path) as f:
            md = f.read()
        start = md.find("---START PROMPT---")
        end = md.find("---END PROMPT---")
        if start >= 0 and end >= 0:
            prompt_text = md[start + len("---START PROMPT---"):end].strip()

    return {"status": "analyzed", "layout": layout, "prompt_template": prompt_text,
            "pages_analyzed": len(layout.get("pages", []))}


@app.post("/api/build-template")
async def build_template_endpoint(data: dict):
    from bank_profile import BankProfile
    from pdf_analyzer import analyze_pdf as _analyze_pdf

    profile_dict = data.get("profile")
    bank_name = data.get("bank_name", "")
    bank_id = data.get("bank_id", "")

    if not profile_dict:
        raise HTTPException(400, "profile is required")
    if not bank_name:
        raise HTTPException(400, "bank_name is required")
    if not bank_id:
        bank_id = bank_name.lower().replace(" ", "_")

    try:
        profile = BankProfile.from_dict(profile_dict)
    except Exception as e:
        raise HTTPException(400, f"Invalid profile: {e}")

    setup_dir = DATA_DIR / "_bank_setup"
    pdf_path = setup_dir / "source.pdf"
    image_dir = setup_dir / "template_images"

    if not pdf_path.exists():
        raise HTTPException(400, "No PDF analyzed yet. Run /api/analyze-pdf first.")

    layout = _analyze_pdf(str(pdf_path), pages=[1, 2], image_dir=str(image_dir))
    footer_data = _extract_last_page_footer(str(pdf_path), profile)

    template = {
        "source_pdf": str(pdf_path),
        "profile": profile_dict,
        "page_width": layout["pages"][0]["width"],
        "page_height": layout["pages"][0]["height"],
        "image_dir": str(image_dir),
        "page1": layout["pages"][0],
        "page2": layout["pages"][1] if len(layout["pages"]) > 1 else None,
        "last_page_footer": footer_data,
    }

    bank_dir = BANKS_DIR / bank_id
    bank_dir.mkdir(parents=True, exist_ok=True)

    dest_images = bank_dir / "template_images"
    if dest_images.exists():
        shutil.rmtree(str(dest_images))
    if image_dir.exists():
        shutil.copytree(str(image_dir), str(dest_images))

    template["image_dir"] = str(dest_images)

    with open(bank_dir / "profile.json", "w") as f:
        json.dump(profile_dict, f, indent=2)

    profiles_dir = bank_dir / "profiles"
    profiles_dir.mkdir(exist_ok=True)
    version = len(list(profiles_dir.glob("profile_v*.json"))) + 1
    with open(profiles_dir / f"profile_v{version}.json", "w") as f:
        json.dump(profile_dict, f, indent=2)

    with open(bank_dir / "template.json", "w") as f:
        json.dump(template, f, indent=2, default=str)

    banks = _load_banks()
    banks = [b for b in banks if b["id"] != bank_id]
    banks.append({
        "id": bank_id, "name": bank_name, "full_name": bank_name, "logo": bank_id,
        "sample_account": {"customer_name": "", "account_number": "", "account_type": "",
                           "current_balance": "0.00", "currency": "INR"},
    })
    with open(BANKS_DIR / "banks.json", "w") as f:
        json.dump(banks, f, indent=2)

    return {"status": "built", "bank_id": bank_id, "bank_name": bank_name,
            "profile_version": version,
            "columns": [c["name"] for c in profile.columns],
            "has_footer": footer_data is not None,
            "footer_spans": len(footer_data["spans"]) if footer_data else 0,
            "header_fields": len(profile.header_fields)}


# ══════════════════════════════════════════════════════════════════════════════
# ACCOUNTS (new hierarchical API)
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/banks/{bank_id}/fields")
def get_bank_fields(bank_id: str):
    """Return the form field schema for a bank (fields.json)."""
    fields_path = BANKS_DIR / bank_id / "fields.json"
    if not fields_path.exists():
        return {"sections": [], "transactionColumns": [], "csvHeaders": "", "csvHeaderMap": {}, "csvExample": ""}
    with open(fields_path) as f:
        data = json.load(f)
    # Support both old format (array) and new format (object)
    if isinstance(data, list):
        return {"sections": data, "transactionColumns": [], "csvHeaders": "", "csvHeaderMap": {}, "csvExample": ""}
    return {
        "sections": data.get("accountSections", []),
        "transactionColumns": data.get("transactionColumns", []),
        "csvHeaders": data.get("csvHeaders", ""),
        "csvHeaderMap": data.get("csvHeaderMap", {}),
        "csvExample": data.get("csvExample", ""),
        "printToPdf": data.get("printToPdf", False),
    }


@app.get("/api/banks/{bank_id}/accounts")
def api_list_accounts(bank_id: str):
    return {"accounts": list_accounts(bank_id)}


@app.post("/api/banks/{bank_id}/accounts")
async def create_account(bank_id: str, data: dict):
    """Create a new account under a bank.

    Body: { "customer_name": "...", "account_number": "...", ...account_data..., "account_id": "optional_slug" }
    """
    _get_template_for_bank(bank_id)  # ensure bank exists

    customer_name = data.get("customer_name", "")
    account_number = data.get("account_number", "")
    custom_slug = data.get("account_id", "")

    if custom_slug:
        slug = custom_slug
    else:
        base_slug = slugify(customer_name, account_number)
        slug = unique_slug(bank_id, base_slug)

    d = get_account_dir(bank_id, slug, create=True)

    # Save account data (exclude account_id from stored data)
    account_data = {k: v for k, v in data.items() if k != "account_id"}
    with open(d / "account_data.json", "w") as f:
        json.dump(account_data, f, indent=2)

    return {"status": "created", "bank_id": bank_id, "account_slug": slug}


@app.get("/api/banks/{bank_id}/accounts/{slug}/data")
def get_account_data_new(bank_id: str, slug: str):
    d = _ensure_account(bank_id, slug)
    fp = d / "account_data.json"
    if not fp.exists():
        # Return sample from bank registry
        banks = _load_banks()
        bank_cfg = next((b for b in banks if b["id"] == bank_id), None)
        if bank_cfg and "sample_account" in bank_cfg:
            return bank_cfg["sample_account"]
        return {}
    with open(fp) as f:
        return json.load(f)


@app.put("/api/banks/{bank_id}/accounts/{slug}/data")
async def save_account_data_new(bank_id: str, slug: str, data: dict):
    d = _ensure_account(bank_id, slug)
    with open(d / "account_data.json", "w") as f:
        json.dump(data, f, indent=2)
    return {"status": "saved"}


# ── Transactions ──────────────────────────────────────────────────────────

@app.post("/api/banks/{bank_id}/accounts/{slug}/transactions")
async def upload_transactions_new(bank_id: str, slug: str, file: UploadFile = File(...)):
    d = _ensure_account(bank_id, slug)
    content = await file.read()
    # Normalize bank-specific headers to internal format
    normalized = _normalize_csv(content, bank_id)
    (d / "transactions.csv").write_bytes(normalized)
    txns = _load_transactions_extended(str(d / "transactions.csv"))
    return {"status": "uploaded", "count": len(txns)}


def _load_transactions_extended(csv_path: str) -> list:
    """Load transactions with all columns including ref and value_date."""
    transactions = []
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            txn = {
                "date": row.get("Date", "").strip(),
                "description": row.get("Description", "").strip(),
                "credit": row.get("Credit", "").strip().replace('"', '').replace(',', ''),
                "debit": row.get("Debit", "").strip().replace('"', '').replace(',', ''),
                "balance": row.get("Balance", "").strip().replace('"', '').replace(',', ''),
                "ref": row.get("Ref", "").strip(),
                "value_date": row.get("Value_Date", "").strip(),
            }
            if txn["date"]:
                transactions.append(txn)
    return transactions


@app.get("/api/banks/{bank_id}/accounts/{slug}/transactions")
def get_transactions_new(bank_id: str, slug: str):
    d = _ensure_account(bank_id, slug)
    fp = d / "transactions.csv"
    if not fp.exists():
        return {"transactions": []}
    txns = _load_transactions_extended(str(fp))
    return {"transactions": txns}


@app.post("/api/banks/{bank_id}/accounts/{slug}/transactions/save")
async def save_transactions_new(bank_id: str, slug: str, data: dict):
    d = _ensure_account(bank_id, slug)
    rows = data.get("transactions", [])
    _write_csv(rows, str(d / "transactions.csv"))
    return {"status": "saved", "count": len(rows)}


@app.post("/api/banks/{bank_id}/accounts/{slug}/transactions/add")
async def add_txn_new(bank_id: str, slug: str, data: dict):
    d = _ensure_account(bank_id, slug)
    csv_path = str(d / "transactions.csv")
    if not (d / "transactions.csv").exists():
        raise HTTPException(400, "No transactions CSV found.")
    txns = load_csv_editor(csv_path)
    new_txns = data.get("transactions", [])
    if not new_txns:
        raise HTTPException(400, "No transactions to add")
    add_transactions_bulk(txns, new_txns)
    save_csv(txns, csv_path)
    return {"status": "added", "added": len(new_txns), "total": len(txns)}


@app.post("/api/banks/{bank_id}/accounts/{slug}/transactions/recalculate")
async def recalc_new(bank_id: str, slug: str):
    d = _ensure_account(bank_id, slug)
    csv_path = str(d / "transactions.csv")
    if not (d / "transactions.csv").exists():
        raise HTTPException(400, "No transactions CSV found.")
    txns = load_csv_editor(csv_path)
    recalculate_balances(txns)
    save_csv(txns, csv_path)
    return {"status": "recalculated", "count": len(txns)}


# ── Generate & Statements ─────────────────────────────────────────────────

@app.post("/api/banks/{bank_id}/accounts/{slug}/generate")
async def generate_new(bank_id: str, slug: str, data: dict = None):
    """Generate PDF using bank template + account data + all transactions."""
    d = _ensure_account(bank_id, slug)
    account_path = d / "account_data.json"
    csv_path = d / "transactions.csv"

    if not account_path.exists():
        raise HTTPException(400, "Account data not found.")
    if not csv_path.exists():
        raise HTTPException(400, "Transactions not found.")

    # Stamp IST timestamps
    _stamp_ist_timestamps(account_path)

    stmts_dir = get_statements_dir(bank_id, slug)
    custom_filename = (data or {}).get("filename", "").strip()
    if custom_filename:
        if not custom_filename.endswith(".pdf"):
            custom_filename += ".pdf"
        output_name = custom_filename
    else:
        output_name = statement_filename("01/01/2000", datetime.now(IST).strftime("%d/%m/%Y"))
    output_path = stmts_dir / output_name

    temp_template = _prepare_template_for_generation(bank_id)
    try:
        generate_pdf(temp_template, str(account_path), str(csv_path), str(output_path))
    except Exception as e:
        raise HTTPException(500, f"PDF generation failed: {e}")
    finally:
        os.unlink(temp_template)

    return {"status": "generated", "filename": output_name, "size": output_path.stat().st_size}


@app.post("/api/banks/{bank_id}/accounts/{slug}/generate-range")
async def generate_range_new(bank_id: str, slug: str, data: dict):
    """Generate PDF for a date range."""
    d = _ensure_account(bank_id, slug)
    account_path = d / "account_data.json"
    csv_path = d / "transactions.csv"

    if not account_path.exists():
        raise HTTPException(400, "Account data not found.")
    if not csv_path.exists():
        raise HTTPException(400, "Transactions not found.")

    # Stamp IST timestamps
    _stamp_ist_timestamps(account_path)

    start_str = data.get("start_date")
    end_str = data.get("end_date")
    if not start_str or not end_str:
        raise HTTPException(400, "Both start_date and end_date are required")

    try:
        start_dt = _parse_date(start_str)
        end_dt = _parse_date(end_str)
    except ValueError as e:
        raise HTTPException(400, str(e))

    all_txns = parse_transactions_csv(str(csv_path))
    filtered = [t for t in all_txns if start_dt <= _parse_date(t["date"]) <= end_dt]

    if not filtered:
        raise HTTPException(400, f"No transactions between {start_str} and {end_str}")

    # Write filtered CSV
    import tempfile
    tf = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, dir=str(d))
    writer = csv.DictWriter(tf, fieldnames=["Date", "Description", "Credit", "Debit", "Balance"])
    writer.writeheader()
    for txn in filtered:
        writer.writerow({"Date": txn["date"], "Description": txn["description"],
                         "Credit": txn["credit"], "Debit": txn["debit"], "Balance": txn["balance"]})
    tf.close()

    stmts_dir = get_statements_dir(bank_id, slug)
    custom_filename = data.get("filename", "").strip()
    if custom_filename:
        if not custom_filename.endswith(".pdf"):
            custom_filename += ".pdf"
        output_name = custom_filename
    else:
        output_name = statement_filename(start_str, end_str)
    output_path = stmts_dir / output_name

    date_range_override = (start_dt.strftime("%d/%m/%Y"), end_dt.strftime("%d/%m/%Y"))

    # Route: HTML engine (pixel-perfect) or ReportLab engine
    engine_used = "reportlab"
    if has_html_layout(bank_id):
        engine_used = "html"
        try:
            generate_pdf_html(bank_id, str(account_path), tf.name, str(output_path),
                              date_range_override=date_range_override)
        except Exception as e:
            raise HTTPException(500, f"HTML PDF generation failed: {e}")
        finally:
            os.unlink(tf.name)
    else:
        temp_template = _prepare_template_for_generation(bank_id)
        try:
            generate_pdf(temp_template, str(account_path), tf.name, str(output_path),
                         date_range_override=date_range_override)
        except Exception as e:
            raise HTTPException(500, f"PDF generation failed: {e}")
        finally:
            os.unlink(tf.name)
            os.unlink(temp_template)

    return {
        "status": "generated", "filename": output_name, "size": output_path.stat().st_size,
        "total_transactions": len(all_txns), "filtered_transactions": len(filtered),
        "date_range": {"start": start_str, "end": end_str},
        "engine": engine_used,
    }


@app.get("/api/banks/{bank_id}/accounts/{slug}/statement-html")
def serve_statement_html(bank_id: str, slug: str, start_date: str = "", end_date: str = ""):
    """Serve the statement as an HTML page for browser print-to-PDF (e.g. HSBC flow)."""
    from fastapi.responses import HTMLResponse

    d = _ensure_account(bank_id, slug)
    account_path = d / "account_data.json"
    csv_path = d / "transactions.csv"

    if not account_path.exists():
        raise HTTPException(400, "Account data not found.")

    # Load account data
    with open(account_path) as f:
        account_data = json.load(f)

    # Stamp IST timestamps
    _stamp_ist_timestamps(account_path)
    with open(account_path) as f:
        account_data = json.load(f)

    # Load and filter transactions
    transactions = []
    if csv_path.exists():
        txns = _load_transactions_extended(str(csv_path))
        if start_date and end_date:
            try:
                start_dt = _parse_date(start_date)
                end_dt = _parse_date(end_date)
                txns = [t for t in txns if start_dt <= _parse_date(t["date"]) <= end_dt]
            except ValueError:
                pass
        transactions = txns

    # Build statement data
    period = {}
    if start_date and end_date:
        period = {"from": start_date, "to": end_date}
    elif transactions:
        dates = [t["date"] for t in transactions if t.get("date")]
        if dates:
            period = {"from": dates[-1], "to": dates[0]}

    statement_data = {
        "account": account_data,
        "transactions": transactions,
        "period": period,
    }

    # Load bank-specific HTML template
    template_path = BANKS_DIR / bank_id / "statement.html"
    if not template_path.exists():
        raise HTTPException(400, f"No HTML statement template for bank: {bank_id}")

    with open(template_path) as f:
        html = f.read()

    # Inject data
    html = html.replace("__STATEMENT_DATA__", json.dumps(statement_data, default=str))

    return HTMLResponse(content=html)


@app.get("/api/banks/{bank_id}/accounts/{slug}/statements")
def list_statements_api(bank_id: str, slug: str):
    _ensure_account(bank_id, slug)
    return {"statements": list_statements(bank_id, slug)}


@app.get("/api/banks/{bank_id}/accounts/{slug}/statements/{filename}")
def download_statement(bank_id: str, slug: str, filename: str):
    stmts_dir = get_statements_dir(bank_id, slug)
    fp = stmts_dir / filename
    if not fp.exists():
        raise HTTPException(404, f"Statement not found: {filename}")
    return FileResponse(str(fp), media_type="application/pdf", filename=filename)


@app.delete("/api/banks/{bank_id}/accounts/{slug}")
async def delete_account(bank_id: str, slug: str):
    d = _ensure_account(bank_id, slug)
    shutil.rmtree(str(d))
    return {"status": "deleted"}


# ══════════════════════════════════════════════════════════════════════════════
# LEGACY API (backward compat for chrome extension + old jobs)
# ══════════════════════════════════════════════════════════════════════════════

def _legacy_job_dir(job_id: str) -> Path:
    """Resolve a legacy job_id to its directory. Checks migration map first."""
    resolved = resolve_legacy_job(job_id)
    if resolved:
        bank_id, slug = resolved
        return get_account_dir(bank_id, slug)

    d = DATA_DIR / job_id
    if d.exists():
        return d
    raise HTTPException(404, f"Job {job_id} not found")


def _legacy_template_path(job_id: str) -> str:
    """Get template path for a legacy job — check migration map for bank template."""
    resolved = resolve_legacy_job(job_id)
    if resolved:
        bank_id, _ = resolved
        return _prepare_template_for_generation(bank_id)

    # Old flat job has its own template
    d = DATA_DIR / job_id
    tp = d / "template.json"
    if tp.exists():
        with open(tp) as f:
            tmpl = json.load(f)
        tmpl["image_dir"] = str(d / tmpl.get("image_dir", "template_images"))
        import tempfile
        tf = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, dir=str(DATA_DIR))
        json.dump(tmpl, tf, indent=2, default=str)
        tf.close()
        return tf.name

    raise HTTPException(400, "No template found for this job")


@app.get("/api/jobs")
def list_jobs_legacy():
    """List all legacy flat jobs + migrated accounts for backward compat."""
    jobs = []

    # List old flat jobs
    for d in sorted(DATA_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        # Skip hierarchical bank directories (they contain subdirs, not job files)
        if (d / "template.json").exists() or not any(
            (d / f).exists() for f in ["account_data.json", "transactions.csv"]
        ):
            # Could be an old flat job with template, or a bank dir — check deeper
            if not (d / "account_data.json").exists():
                continue

        has_txns = (d / "transactions.csv").exists()
        if not has_txns:
            continue

        label = d.name
        try:
            with open(d / "account_data.json") as f:
                acct = json.load(f)
            name = acct.get("customer_name", "")
            acct_num = acct.get("account_number", "")
            label = f"{name} - {acct_num}" if name else d.name
        except Exception:
            pass

        txn_count = 0
        try:
            txns = parse_transactions_csv(str(d / "transactions.csv"))
            txn_count = len(txns)
        except Exception:
            pass

        jobs.append({"job_id": d.name, "label": label, "txn_count": txn_count,
                     "has_output": (d / "output.pdf").exists()})

    return {"jobs": jobs}


@app.post("/api/jobs/{job_id}/generate-range")
async def generate_range_legacy(job_id: str, data: dict):
    """Legacy endpoint for chrome extension."""
    d = _legacy_job_dir(job_id)
    account_path = d / "account_data.json"
    csv_path = d / "transactions.csv"

    for fp, label in [(account_path, "Account data"), (csv_path, "Transactions")]:
        if not fp.exists():
            raise HTTPException(400, f"{label} not found.")

    start_str = data.get("start_date")
    end_str = data.get("end_date")
    if not start_str or not end_str:
        raise HTTPException(400, "Both start_date and end_date are required")

    start_dt = _parse_date(start_str)
    end_dt = _parse_date(end_str)

    all_txns = parse_transactions_csv(str(csv_path))
    filtered = [t for t in all_txns if start_dt <= _parse_date(t["date"]) <= end_dt]

    if not filtered:
        raise HTTPException(400, f"No transactions between {start_str} and {end_str}")

    import tempfile
    tf = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False)
    writer = csv.DictWriter(tf, fieldnames=["Date", "Description", "Credit", "Debit", "Balance"])
    writer.writeheader()
    for txn in filtered:
        writer.writerow({"Date": txn["date"], "Description": txn["description"],
                         "Credit": txn["credit"], "Debit": txn["debit"], "Balance": txn["balance"]})
    tf.close()

    output_path = d / "output.pdf"
    date_range_override = (start_dt.strftime("%d/%m/%Y"), end_dt.strftime("%d/%m/%Y"))
    temp_template = _legacy_template_path(job_id)

    try:
        generate_pdf(temp_template, str(account_path), tf.name, str(output_path),
                     date_range_override=date_range_override)
    except Exception as e:
        raise HTTPException(500, f"PDF generation failed: {e}")
    finally:
        os.unlink(tf.name)
        if os.path.exists(temp_template):
            os.unlink(temp_template)

    # Also save to statements/ if this is a migrated account
    resolved = resolve_legacy_job(job_id)
    if resolved:
        stmts_dir = get_statements_dir(resolved[0], resolved[1])
        stmt_name = statement_filename(start_str, end_str)
        shutil.copy2(str(output_path), str(stmts_dir / stmt_name))

    return {
        "status": "generated", "size": output_path.stat().st_size,
        "total_transactions": len(all_txns), "filtered_transactions": len(filtered),
        "date_range": {"start": start_str, "end": end_str},
    }


@app.get("/api/jobs/{job_id}/download")
def download_legacy(job_id: str):
    d = _legacy_job_dir(job_id)
    fp = d / "output.pdf"
    if not fp.exists():
        raise HTTPException(404, "PDF not generated yet")
    return FileResponse(str(fp), media_type="application/pdf", filename="statement.pdf")


# ══════════════════════════════════════════════════════════════════════════════
# SERVE FRONTEND
# ══════════════════════════════════════════════════════════════════════════════

frontend_dist = Path(__file__).parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
