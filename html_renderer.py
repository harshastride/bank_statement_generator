"""
HTML-based PDF Statement Generator
====================================
Generates pixel-perfect bank statement PDFs using:
  1. Generic HTML engine (html_engine/)
  2. Bank-specific layout JSON (banks/{bank_id}/layout.json)
  3. Headless Chromium via Playwright (or Puppeteer fallback)

Usage:
    from html_renderer import generate_pdf_html
    generate_pdf_html(bank_id, account_data, transactions, output_path, date_range=None)
"""

import csv
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
BANKS_DIR = BASE_DIR / "banks"
ENGINE_DIR = BASE_DIR / "html_engine"


def _parse_num(value):
    """Parse a number from string, handling commas."""
    if not value:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(",", "").replace('"', '').strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _load_layout(bank_id):
    """Load the bank's layout.json."""
    layout_path = BANKS_DIR / bank_id / "layout.json"
    if not layout_path.exists():
        raise FileNotFoundError(f"No layout.json found for bank '{bank_id}' at {layout_path}")
    with open(layout_path) as f:
        return json.load(f)


def _shorten_date(d):
    """Convert DD/MM/YYYY → DD/MM/YY."""
    if not d:
        return ""
    import re
    m = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', str(d).strip())
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)[2:]}"
    return str(d)


def _build_statement_data(account_data, transactions, date_range=None):
    """Convert V2's account_data + transaction list → statementData JS object."""
    txn_list = []
    for t in transactions:
        desc = t.get("description", t.get("narration", ""))

        # For CSV data: narration is single line, no details
        # For PDF-extracted data: may have narration + details
        if t.get("narration") and t.get("details"):
            narration = t["narration"]
            details = t.get("details", [])
            if isinstance(details, str):
                details = [details] if details else []
        elif "\n" in desc:
            parts = desc.split("\n")
            narration = parts[0]
            details = parts[1:]
        else:
            # CSV single-line narration — NO details, engine will truncate via CSS
            narration = desc
            details = []

        raw_date = t.get("date", "")
        raw_vdate = t.get("value_date", t.get("valueDate", raw_date))

        txn_list.append({
            "date": _shorten_date(raw_date),
            "narration": narration,
            "details": details,
            "reference": t.get("ref", t.get("reference", t.get("chq_ref", ""))),
            "valueDate": _shorten_date(raw_vdate),
            "withdrawal": _parse_num(t.get("debit", t.get("withdrawal", 0))),
            "deposit": _parse_num(t.get("credit", t.get("deposit", 0))),
        })

    # Calculate opening balance
    if txn_list:
        first_txn = txn_list[0]
        w = first_txn.get("withdrawal", 0) or 0
        d = first_txn.get("deposit", 0) or 0
        first_balance = _parse_num(transactions[0].get("balance", 0))
        opening_balance = first_balance - d + w
    else:
        opening_balance = _parse_num(account_data.get("current_balance", 0))

    # Use explicit opening_balance from account_data if available
    if account_data.get("opening_balance"):
        ob = _parse_num(account_data["opening_balance"])
        if ob > 0:
            opening_balance = ob

    # Determine date range
    if date_range:
        period_from, period_to = date_range
    elif account_data.get("statement_from") and account_data.get("statement_to"):
        period_from = account_data["statement_from"]
        period_to = account_data["statement_to"]
    elif txn_list:
        dates = [t["date"] for t in txn_list if t.get("date")]
        # CSV is typically newest-first, so last date = earliest
        period_from = dates[-1] if dates else ""
        period_to = dates[0] if dates else ""
    else:
        period_from, period_to = "", ""

    # Build V3-compatible data structure
    # account.holder = array of left-side customer details
    a = account_data
    holder = a.get("holder", [
        a.get("customer_name", ""),
        a.get("address_line_1", ""),
        a.get("address_line_2", ""),
        a.get("city_state", ""),
        a.get("pin", ""),
        a.get("state_country", ""),
        "",
        "JOINT HOLDERS :" + (" " + a["joint_holders"] if a.get("joint_holders") else ""),
    ])

    # branch = array of [label, value] pairs for right-side header (exactly 17 entries)
    acct_no = a.get("account_number", "")
    acct_variant = a.get("account_variant", "")
    acct_no_display = f"{acct_no}    {acct_variant}" if acct_variant else acct_no

    ifsc = a.get("ifsc", "")
    micr = a.get("micr", "")
    ifsc_display = f"{ifsc}         MICR : {micr}" if micr else ifsc

    branch = [
        ["Account Branch", a.get("branch", "")],
        ["Address", a.get("branch_address_1", "")],
        ["", a.get("branch_address_2", "")],
        ["", a.get("branch_address_3", "")],
        ["City", a.get("branch_city", "")],
        ["State", a.get("branch_state", "")],
        ["Phone no.", a.get("phone", "")],
        ["OD Limit", a.get("overdraft", "0.00")],
        ["Currency", a.get("currency", "INR")],
        ["Email", a.get("email", "")],
        ["Cust ID", a.get("cust_id", "")],
        ["Account No", acct_no_display],
        ["A/C Open Date", a.get("ac_open_date", "")],
        ["Account Status", a.get("account_status", "")],
        ["RTGS/NEFT IFSC", ifsc_display],
        ["Branch Code", a.get("branch_code", "")],
        ["Account Type", a.get("account_type", "")],
    ]

    return {
        "account": {
            "holder": holder,
            "nomination": a.get("nominee", a.get("nomination", "")),
        },
        "branch": branch,
        "period": {
            "from": period_from,
            "to": period_to,
        },
        "openingBalance": opening_balance,
        "generatedOn": a.get("generated_on", ""),
        "generatedBy": a.get("generated_by", a.get("cust_id", "")),
        "requestingBranchCode": a.get("requesting_branch_code", "NET"),
        "transactions": txn_list,
    }


def _parse_csv_for_html(csv_path):
    """Parse CSV file into transaction dicts for the HTML engine."""
    transactions = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            txn = {}
            for key, value in row.items():
                clean_key = key.strip().lower().replace(" ", "_").replace(".", "").replace("/", "_")
                txn[clean_key] = value.strip() if value else ""

            # Normalize keys — handle various CSV column naming conventions
            normalized = {
                "date": txn.get("date", ""),
                "description": txn.get("description", txn.get("narration", "")),
                "credit": txn.get("credit", txn.get("deposit_amt", txn.get("deposit_amt_", txn.get("deposit", "")))),
                "debit": txn.get("debit", txn.get("withdrawal_amt", txn.get("withdrawal_amt_", txn.get("withdrawal", "")))),
                "balance": txn.get("balance", txn.get("closing_balance", "")),
                "ref": txn.get("chq_refno", txn.get("chq__refno", txn.get("chq_ref_no", txn.get("ref", txn.get("reference", ""))))),
                "value_date": txn.get("value_dt", txn.get("value_date", "")),
            }
            if normalized["date"]:
                transactions.append(normalized)

    return transactions


def _build_html(layout, statement_data, logo_path=None):
    """Build a self-contained HTML string with inlined data + engine."""
    engine_css = (ENGINE_DIR / "engine.css").read_text()
    engine_js = (ENGINE_DIR / "engine.js").read_text()

    # Fix logo src to absolute path or data URI
    if logo_path and os.path.exists(logo_path):
        import base64
        with open(logo_path, "rb") as f:
            logo_data = base64.b64encode(f.read()).decode()
        ext = os.path.splitext(logo_path)[1].lower()
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
        layout["logo"]["src"] = f"data:{mime};base64,{logo_data}"

    data_json = json.dumps(statement_data, ensure_ascii=False)
    layout_json = json.dumps(layout, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Bank Statement</title>
  <style>{engine_css}</style>
</head>
<body>
  <main class="precise-workspace">
    <div id="preciseStatementPages" class="precise-pages"></div>
  </main>
  <script>window.statementData = {data_json};</script>
  <script>window.statementPreciseLayout = {layout_json};</script>
  <script>{engine_js}</script>
</body>
</html>"""


def _find_logo(bank_id):
    """Find the bank's logo image."""
    # Check bank root first, then template_images
    bank_dir = BANKS_DIR / bank_id
    img_dir = bank_dir / "template_images"
    for search_dir in [bank_dir, img_dir]:
        for name in ["logo.jpg", "logo.jpeg", "logo.png", "page1_img0.jpeg", "page1_img0.png"]:
            path = search_dir / name
            if path.exists():
                return str(path)
    return None


def _convert_html_to_pdf_playwright(html_path, output_path, page_width, page_height):
    """Convert HTML to PDF using Playwright (preferred)."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"file://{html_path}", wait_until="networkidle")
            page.wait_for_timeout(500)

            # Playwright expects width/height as strings like "638px" or numbers in pixels
            # Convert pt to px (1pt = 1.3333px at 96dpi)
            px_w = f"{page_width * 96 / 72:.0f}px"
            px_h = f"{page_height * 96 / 72:.0f}px"
            page.pdf(
                path=str(output_path),
                width=px_w,
                height=px_h,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                print_background=True,
                prefer_css_page_size=True,
            )
            browser.close()
        return True
    except ImportError:
        return False
    except Exception as e:
        print(f"Playwright failed: {e}")
        return False


def _convert_html_to_pdf_node(html_path, output_path, page_width, page_height):
    """Convert HTML to PDF using Node.js puppeteer script."""
    puppeteer_script = f"""
const puppeteer = require('puppeteer');
(async () => {{
  const browser = await puppeteer.launch({{ headless: 'new' }});
  const page = await browser.newPage();
  await page.goto('file://{html_path}', {{ waitUntil: 'networkidle0' }});
  await page.pdf({{
    path: '{output_path}',
    width: '{page_width}pt',
    height: '{page_height}pt',
    margin: {{ top: '0', right: '0', bottom: '0', left: '0' }},
    printBackground: true,
    preferCSSPageSize: true,
  }});
  await browser.close();
}})();
"""
    script_path = Path(tempfile.mktemp(suffix=".js"))
    try:
        script_path.write_text(puppeteer_script)
        result = subprocess.run(
            ["node", str(script_path)],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"Puppeteer error: {result.stderr}")
            return False
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"Node/Puppeteer not available: {e}")
        return False
    finally:
        script_path.unlink(missing_ok=True)


def _convert_html_to_pdf_chrome(html_path, output_path, page_width, page_height):
    """Convert HTML to PDF using Chrome/Chromium headless (no extra deps)."""
    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    chrome = next((p for p in chrome_paths if p and os.path.exists(p)), None)
    if not chrome:
        return False

    try:
        result = subprocess.run(
            [
                chrome,
                "--headless",
                "--disable-gpu",
                "--no-sandbox",
                f"--print-to-pdf={output_path}",
                "--no-pdf-header-footer",
                f"--print-to-pdf-no-header",
                f"file://{html_path}",
            ],
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0 and os.path.exists(output_path)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print(f"Chrome headless failed: {e}")
        return False


def generate_pdf_html(bank_id, account_data_path, csv_path, output_path,
                      date_range_override=None):
    """
    Generate a pixel-perfect PDF using the HTML engine.

    Args:
        bank_id: Bank identifier (e.g., 'hdfc_bank')
        account_data_path: Path to account_data.json
        csv_path: Path to transactions CSV
        output_path: Where to save the PDF
        date_range_override: Optional (start_date, end_date) tuple
    """
    # Load inputs
    layout = _load_layout(bank_id)
    with open(account_data_path) as f:
        account_data = json.load(f)

    transactions = _parse_csv_for_html(csv_path)
    if not transactions:
        raise ValueError("No transactions found in CSV")

    print(f"[HTML Engine] Loaded {len(transactions)} transactions for {bank_id}")

    # Build statement data
    statement_data = _build_statement_data(
        account_data, transactions, date_range=date_range_override
    )

    # Find logo
    logo_path = _find_logo(bank_id)

    # Build self-contained HTML
    html_content = _build_html(layout, statement_data, logo_path)

    # Write to temp file
    tmp_dir = tempfile.mkdtemp(prefix="stmt_html_")
    html_path = os.path.join(tmp_dir, "statement.html")
    with open(html_path, "w") as f:
        f.write(html_content)

    page_w = layout.get("pageWidth", 638)
    page_h = layout.get("pageHeight", 842)

    print(f"[HTML Engine] Rendering PDF ({page_w}x{page_h}pt)...")

    # Try renderers in order of preference
    success = _convert_html_to_pdf_playwright(html_path, output_path, page_w, page_h)

    if not success:
        print("[HTML Engine] Playwright not available, trying Puppeteer...")
        success = _convert_html_to_pdf_node(html_path, output_path, page_w, page_h)

    if not success:
        print("[HTML Engine] Puppeteer not available, trying Chrome headless...")
        success = _convert_html_to_pdf_chrome(html_path, output_path, page_w, page_h)

    # Cleanup
    try:
        shutil.rmtree(tmp_dir)
    except Exception:
        pass

    if not success:
        raise RuntimeError(
            "PDF generation failed. Install one of:\n"
            "  1. pip install playwright && playwright install chromium\n"
            "  2. npm install -g puppeteer\n"
            "  3. Install Google Chrome / Chromium"
        )

    size = os.path.getsize(output_path)
    print(f"[HTML Engine] Done! → {output_path} ({size:,} bytes)")
    return output_path


def has_html_layout(bank_id):
    """Check if a bank has an HTML layout.json (vs only ReportLab profile)."""
    return (BANKS_DIR / bank_id / "layout.json").exists()


# ── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate PDF from HTML engine")
    parser.add_argument("bank_id", help="Bank identifier (e.g., hdfc_bank)")
    parser.add_argument("account_data", help="Path to account_data.json")
    parser.add_argument("csv_path", help="Path to transactions CSV")
    parser.add_argument("-o", "--output", default="statement.pdf", help="Output PDF path")
    parser.add_argument("--start-date", help="Start date (DD/MM/YYYY)")
    parser.add_argument("--end-date", help="End date (DD/MM/YYYY)")
    args = parser.parse_args()

    dr = None
    if args.start_date and args.end_date:
        dr = (args.start_date, args.end_date)

    generate_pdf_html(args.bank_id, args.account_data, args.csv_path, args.output,
                      date_range_override=dr)
