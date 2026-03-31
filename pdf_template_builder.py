"""
PDF Template Builder — Extract a layout template from any PDF, then generate
new PDFs by swapping in different account data and transactions.

The template preserves the EXACT table grid structure (rects/borders) from the
original PDF. Text flows naturally into the grid cells, splitting across pages
just like the original document.

Now supports dynamic bank profiles — all layout parameters are auto-detected
from the source PDF and stored in the template, eliminating hardcoded constants.

Usage:
    python pdf_template_builder.py create-template --pdf statement.pdf
    python pdf_template_builder.py sample-data
    python pdf_template_builder.py generate -t template.json -d account_data.json -c transactions.csv -o output.pdf
"""

import argparse
import copy
import csv
import json
import os

from reportlab.pdfbase.pdfmetrics import stringWidth

from pdf_analyzer import analyze_pdf
from pdf_rebuilder import rebuild_pdf
from bank_profile import BankProfile, DEFAULT_HSBC_PROFILE


# ── Helpers ─────────────────────────────────────────────────────────────────

def _tb(text, x, y, font_spec, x1=None):
    """Create a text block dict."""
    return {
        "text": str(text), "x": x, "y": y,
        "x1": x1 or (x + len(str(text)) * font_spec["size"] * 0.5),
        "y1": y + font_spec["size"],
        "font": font_spec["font"], "size": font_spec["size"], "color": font_spec["color"],
    }


def _parse_num(value):
    """Parse a string amount to float. Returns 0.0 for empty/invalid."""
    if not value:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(",", "").replace('"', '').strip()
    if not cleaned:
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _fmt_amt(value):
    """Format amount with commas and 2 decimals."""
    if isinstance(value, str):
        value = value.replace(",", "").replace('"', '')
        try:
            value = float(value)
        except ValueError:
            return value
    return f"{value:,.2f}"


def _fmt_date(date_str):
    """DD/MM/YY → DD/MM/YYYY."""
    parts = date_str.strip().split("/")
    if len(parts) == 3 and len(parts[2]) == 2:
        return f"{parts[0]}/{parts[1]}/{2000 + int(parts[2])}"
    return date_str


def _right_x(text, right_edge, font_size, font_name="ArialMT"):
    """Calculate x for right-aligned text using actual font metrics."""
    from pdf_rebuilder import map_font, _register_ttf_fonts
    _register_ttf_fonts()
    mapped = map_font(font_name)
    w = stringWidth(text, mapped, font_size)
    return right_edge - w


def _wrap_text(text, max_width, font_size):
    """Word-wrap text to fit within max_width."""
    max_chars = int(max_width / (font_size * 0.48))
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        if len(test) <= max_chars:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _load_profile(template):
    """Load BankProfile from template dict. Falls back to DEFAULT_HSBC_PROFILE."""
    if "profile" in template:
        return BankProfile.from_dict(template["profile"])
    return DEFAULT_HSBC_PROFILE


# ── Template creation ───────────────────────────────────────────────────────

def _extract_last_page_footer(pdf_path, profile=None):
    """Extract footer content (disclaimer, GSTN table, etc.) from the last page.

    Finds all text below the last transaction and captures it as positioned
    text blocks with colors, links, and the surrounding border rect.
    Returns a dict with the footer data relative to a start_y of 0.
    """
    import fitz as _fitz

    if profile is None:
        profile = DEFAULT_HSBC_PROFILE

    doc = _fitz.open(pdf_path)
    last_page = doc[-1]
    data = last_page.get_text("dict")

    txn_font_size = profile.fonts.get("transaction", {}).get("size", 8.51)

    # Find the last transaction text using column positions from profile
    last_txn_y = 0
    date_col = profile.get_column("date")
    desc_col = profile.get_column("description")
    date_x = date_col["x"] if date_col else 53.9
    desc_x = desc_col["x"] if desc_col else 138.3

    for block in data["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if abs(span["size"] - txn_font_size) < 1.0 and span["bbox"][1] > last_txn_y:
                    x_rounded = round(span["origin"][0])
                    text = span["text"].strip()
                    # Skip browser chrome at page edges
                    if x_rounded < 30 or span["bbox"][1] > profile.page_height - 30:
                        continue
                    is_date_col = abs(x_rounded - date_x) <= 2
                    is_desc_col = abs(x_rounded - desc_x) <= 2
                    is_amount = (x_rounded > 300 and
                                len(text) > 0 and (text[0].isdigit() or text[0] == ' '))
                    if is_date_col or is_desc_col or is_amount:
                        last_txn_y = span["bbox"][1]

    # Footer starts after a gap from last transaction
    footer_spans = []
    footer_start_y = None
    for block in data["blocks"]:
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                y = span["bbox"][1]
                if y > last_txn_y + 20 and y < profile.footer_y:
                    if footer_start_y is None:
                        footer_start_y = y
                    color_int = span["color"]
                    r_c = (color_int >> 16) & 0xFF
                    g_c = (color_int >> 8) & 0xFF
                    b_c = color_int & 0xFF
                    hex_color = f"#{r_c:02X}{g_c:02X}{b_c:02X}"

                    footer_spans.append({
                        "text": span["text"],
                        "x": round(span["origin"][0], 1),
                        "y": round(y, 1),
                        "size": round(span["size"], 2),
                        "color": hex_color,
                        "font": span.get("font", "ArialMT"),
                    })

    if not footer_spans or footer_start_y is None:
        doc.close()
        return None

    # Get links on last page
    links = last_page.get_links()
    link_rects = []
    for lnk in links:
        if lnk.get("uri"):
            link_rects.append({
                "uri": lnk["uri"],
                "x0": round(lnk["from"].x0, 1),
                "y0": round(lnk["from"].y0, 1),
                "x1": round(lnk["from"].x1, 1),
                "y1": round(lnk["from"].y1, 1),
            })

    # Get the border rect around footer
    footer_border = None
    drawings = last_page.get_drawings()
    for d in drawings:
        rect = d["rect"]
        color = d.get("color")
        fill = d.get("fill")
        if rect.y0 > last_txn_y + 10 and rect.height > 100:
            has_stroke = color and color != (1.0, 1.0, 1.0)
            has_fill = fill and fill != (1.0, 1.0, 1.0)
            if has_stroke or has_fill:
                stroke_color = color or fill
                footer_border = {
                    "x0": round(rect.x0, 1),
                    "y0": round(rect.y0, 1),
                    "x1": round(rect.x1, 1),
                    "y1": round(rect.y1, 1),
                    "color": [round(c, 2) for c in stroke_color],
                }
                break

    gap = round(footer_start_y - last_txn_y, 1)

    # Make spans relative to footer_start_y
    relative_spans = []
    for s in footer_spans:
        rel = copy.deepcopy(s)
        rel["y_offset"] = round(s["y"] - footer_start_y, 1)
        for lnk in link_rects:
            if (abs(s["y"] - lnk["y0"]) < 5 and
                abs(s["x"] - lnk["x0"]) < 5 and
                s["color"] == "#0000EE"):
                rel["link"] = lnk["uri"]
        relative_spans.append(rel)

    # Footer border relative
    rel_border = None
    if footer_border:
        rel_border = {
            "x0": footer_border["x0"],
            "y_offset": round(footer_border["y0"] - footer_start_y, 1),
            "x1": footer_border["x1"],
            "height": round(footer_border["y1"] - footer_border["y0"], 1),
        }

    last_span_y = max(s["y"] for s in footer_spans)
    total_height = round(last_span_y - footer_start_y + 20, 1)

    doc.close()

    return {
        "gap_from_last_txn": gap,
        "spans": relative_spans,
        "border": rel_border,
        "total_height": total_height,
    }


def create_template(pdf_path, output_path, image_dir="template_images"):
    """Extract template from existing PDF (pages 1, 2, and last page footer).

    Auto-detects layout profile and embeds it in the template.
    """
    print(f"Creating template from '{pdf_path}'...")
    layout = analyze_pdf(pdf_path, pages=[1, 2], image_dir=image_dir)

    # Auto-detect layout profile
    print("  Detecting layout profile...")
    from layout_detector import detect_layout
    profile = detect_layout(layout)
    print(f"  Profile: {len(profile.columns)} columns, "
          f"page={profile.page_width}x{profile.page_height}")

    # Extract last page footer content
    print("  Extracting last page footer...")
    footer_data = _extract_last_page_footer(pdf_path, profile)
    if footer_data:
        print(f"  Footer: {len(footer_data['spans'])} text spans, gap={footer_data['gap_from_last_txn']}pt")
    else:
        print("  No footer content found")

    template = {
        "source_pdf": pdf_path,
        "profile": profile.to_dict(),
        "page_width": layout["pages"][0]["width"],
        "page_height": layout["pages"][0]["height"],
        "image_dir": image_dir,
        "page1": layout["pages"][0],
        "page2": layout["pages"][1] if len(layout["pages"]) > 1 else None,
        "last_page_footer": footer_data,
    }
    with open(output_path, "w") as f:
        json.dump(template, f, indent=2, default=str)
    print(f"Template saved → {output_path}")
    print(f"Images saved → {image_dir}/")
    return template


# ── Line-based content generation ───────────────────────────────────────────

def _generate_all_text_lines(transactions, profile):
    """Convert transactions into a flat list of text lines to place in the table.

    Uses profile for column positions and fonts instead of hardcoded constants.
    """
    font_txn = profile.get_font("transaction")

    # Get column positions by role
    date_x = profile.get_column_x("date", 53.9)
    desc_x = profile.get_column_x("description", 138.3)

    credit_col = profile.get_column("credit")
    debit_col = profile.get_column("debit")
    balance_col = profile.get_column("balance")

    credit_right_x = credit_col["x"] if credit_col else 337.3
    debit_right_x = debit_col["x"] if debit_col else 437.2
    balance_right_x = balance_col["x"] if balance_col else 537.0

    items = []
    for txn in transactions:
        desc = txn["description"]
        if " | " in desc:
            desc_parts = desc.split(" | ")
        elif " - " in desc:
            desc_parts = desc.split(" - ", 1)
        else:
            desc_parts = [desc]
        txn_type = desc_parts[0].strip() if desc_parts else "TRANSFER"

        # Summary line
        summary_blocks = []
        summary_blocks.append(_tb(_fmt_date(txn["date"]), date_x, 0, font_txn))
        summary_blocks.append(_tb(txn_type, desc_x, 0, font_txn))

        credit_val = _parse_num(txn.get("credit", ""))
        debit_val = _parse_num(txn.get("debit", ""))

        if credit_val > 0:
            t = f" {_fmt_amt(credit_val)}"
            summary_blocks.append(_tb(t, _right_x(t, credit_right_x, font_txn["size"], font_txn["font"]), 0, font_txn))
        if debit_val > 0:
            t = f" {_fmt_amt(debit_val)}"
            summary_blocks.append(_tb(t, _right_x(t, debit_right_x, font_txn["size"], font_txn["font"]), 0, font_txn))

        bal = f" {_fmt_amt(txn['balance'])}"
        summary_blocks.append(_tb(bal, _right_x(bal, balance_right_x, font_txn["size"], font_txn["font"]), 0, font_txn))

        items.append({"type": "summary", "blocks": summary_blocks})

        # Detail lines
        for part in desc_parts:
            items.append({"type": "detail", "blocks": [_tb(part.strip(), desc_x, 0, font_txn)]})

    return items


# ── Page 1 header ───────────────────────────────────────────────────────────

def _build_page1_header(account, date_range, total_pages, profile):
    """Build page 1 static header blocks (everything above transactions)."""
    blocks = []

    chrome = profile.browser_chrome
    chrome_font = profile.get_font("browser_chrome")

    # Build header from profile header_fields
    for field in profile.header_fields:
        font_key = field.get("font_key", "label")

        # Use the original_font if present (auto-detected), otherwise use profile font
        if "original_font" in field:
            font_spec = field["original_font"]
        else:
            font_spec = profile.get_font(font_key)

        template_text = field.get("template", "")

        # Substitute {placeholders} with account data
        text = template_text
        for key, value in account.items():
            placeholder = "{" + key + "}"
            if placeholder in text:
                if key == "current_balance":
                    text = text.replace(placeholder, _fmt_amt(value))
                elif key in ("download_date",):
                    text = text.replace(placeholder, _fmt_date(str(value)))
                else:
                    text = text.replace(placeholder, str(value))

        # Skip fields with unresolved {placeholders} — Claude may have used
        # placeholder names that don't match account_data keys
        import re
        if re.search(r'\{[a-z_]+\}', text):
            continue

        # Handle right-aligned balance
        if field.get("role") == "current_balance_right":
            x = _right_x(text, field["x"], font_spec["size"], font_spec["font"])
        else:
            x = field["x"]

        blocks.append(_tb(text, x, field["y"], font_spec))

    # Date range display (if present)
    if date_range:
        from pdf_rebuilder import map_font, _register_ttf_fonts
        _register_ttf_fonts()
        label_font = profile.get_font("label")
        name_font = profile.get_font("name")

        # Position date range below "Search results" heading
        # Find the heading Y to place date range below it
        heading_y = 348.3  # default
        for f in profile.header_fields:
            if f.get("template") == "Search results":
                heading_y = f["y"]
                break
        date_range_y = heading_y + 17.4

        blocks.append(_tb("Date range:", 42.8, date_range_y, label_font))
        start_str = _fmt_date(date_range[0])
        end_str = _fmt_date(date_range[1])
        start_x = 87.0
        start_w = stringWidth(start_str, map_font(name_font["font"]), name_font["size"])
        dash_x = start_x + start_w + 4
        dash_w = stringWidth(" - ", map_font(name_font["font"]), name_font["size"])
        end_x = dash_x + dash_w
        blocks.append(_tb(start_str, start_x, date_range_y, name_font))
        blocks.append(_tb("-", dash_x, date_range_y, name_font))
        blocks.append(_tb(end_str, end_x, date_range_y, name_font))

    # Table header row from profile columns
    table_header_font = profile.get_font("table_header")
    for col in profile.columns:
        col_font = col.get("font", table_header_font)
        blocks.append(_tb(col["name"], col["header_x"], profile.p1_table_header_y, col_font))

    # Browser chrome footer
    blocks.append(_tb(chrome.get("url_text", "about:blank"), 24.0, profile.footer_y, chrome_font))
    blocks.append(_tb(f"1/{total_pages}", chrome.get("page_num_x", 551.2), profile.footer_y, chrome_font))

    return blocks


def _build_cont_page_header(page_num, total_pages, print_date, print_time, profile):
    """Build continuation page header — minimal header + browser chrome."""
    blocks = []
    chrome = profile.browser_chrome
    chrome_font = profile.get_font("browser_chrome")

    blocks.append(_tb(f"{print_date}, {print_time}", 24.0, chrome.get("top_y", 15.9), chrome_font))
    blocks.append(_tb(chrome.get("title_text", ""), 280.6, chrome.get("top_y", 15.9), chrome_font))

    # Continuation header fields (e.g., just "Balance" column header)
    table_header_font = profile.get_font("table_header")
    for field in profile.cont_header_fields:
        f = profile.get_font(field.get("font_key", "table_header"))
        blocks.append(_tb(field["text"], field["x"], profile.cont_header_text_y, f))

    blocks.append(_tb(chrome.get("url_text", "about:blank"), 24.0, profile.footer_y, chrome_font))
    blocks.append(_tb(f"{page_num}/{total_pages}", chrome.get("page_num_x", 551.2), profile.footer_y, chrome_font))
    return blocks


# ── Dynamic grid rect generation ────────────────────────────────────────────

def _make_rect(x0, y0, x1, y1, color=None, default_color=None):
    """Create a rect dict with given color for both fill and stroke."""
    c = color or default_color or [0.8, 0.8, 0.8]
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "fill_color": c, "stroke_color": c, "width": 0.75}


def _generate_grid_rects(page_rows, table_top, profile, is_last_txn_page=False):
    """Generate the table grid rects dynamically based on content rows.

    If profile has rect patterns (header_row_rects_pattern, etc.), stamps them.
    Otherwise falls back to col_bounds-based generation.
    """
    gap = profile.text_to_border_gap
    col_bounds = profile.col_bounds
    border_color = profile.grid_colors.get("border", [0.8, 0.8, 0.8])

    has_patterns = bool(profile.header_row_rects_pattern)

    if not has_patterns and (not col_bounds or len(col_bounds) < 2):
        return []

    left_edge = col_bounds[0] if col_bounds else 42.8
    right_edge = col_bounds[-1] if col_bounds else 553.5

    rects = []

    for row_type, text_y, row_height in page_rows:
        border_y = text_y - gap
        row_bottom = border_y + row_height

        # Select the pattern for this row type
        if has_patterns:
            if row_type == "header":
                pattern = profile.header_row_rects_pattern
            elif row_type == "summary":
                pattern = profile.summary_row_rects_pattern
            elif row_type == "detail":
                pattern = profile.detail_row_rects_pattern
            else:
                continue

            for pr in pattern:
                # Determine Y position
                if pr.get("at_row_bottom"):
                    y0 = row_bottom + pr.get("y_offset_from_bottom", 0)
                else:
                    y0 = border_y + pr.get("y_offset", 0)

                # Determine height
                if pr.get("use_row_height"):
                    h = row_height - pr.get("y_offset", 0)
                else:
                    h = pr["height"]

                rects.append({
                    "x0": pr["x0"], "x1": pr["x1"],
                    "y0": y0, "y1": y0 + h,
                    "fill_color": pr.get("fill_color"),
                    "stroke_color": pr.get("stroke_color"),
                    "width": pr.get("width", 0.75),
                })
        else:
            # Fallback: no patterns, skip (should not happen with DEFAULT_HSBC_PROFILE)
            pass

    # Closing horizontal line
    if page_rows and is_last_txn_page:
        last_border_y = page_rows[-1][1] - gap
        last_bottom = last_border_y + page_rows[-1][2]
        closing_cols = profile.closing_col_segments or col_bounds
        for i in range(len(closing_cols) - 1):
            rects.append(_make_rect(closing_cols[i], last_bottom, closing_cols[i + 1], last_bottom + 0.53, border_color))

    # Outer table background
    if page_rows:
        first_border_y = page_rows[0][1] - gap
        last_border_y = page_rows[-1][1] - gap
        last_bottom = last_border_y + page_rows[-1][2]
        bg_top = min(table_top, first_border_y)
        rects.insert(0, _make_rect(left_edge, bg_top, right_edge, last_bottom + 1, [1.0, 1.0, 1.0]))

    return rects


# ── Disclaimer ──────────────────────────────────────────────────────────────

def _build_footer_from_template(start_y, footer_data):
    """Build footer blocks dynamically from extracted template footer data."""
    if not footer_data:
        return [], [], 0

    blocks = []
    rects = []

    for span in footer_data["spans"]:
        y = start_y + span["y_offset"]
        font_spec = {
            "font": span.get("font", "ArialMT"),
            "size": span["size"],
            "color": span["color"],
        }
        b = _tb(span["text"], span["x"], y, font_spec)
        if span.get("link"):
            b["link"] = span["link"]
        blocks.append(b)

    border = footer_data.get("border")
    if border:
        border_y = start_y + border["y_offset"]
        border_color = border.get("color", [0.2, 0.2, 0.2])
        rects.append({
            "x0": border["x0"],
            "y0": border_y,
            "x1": border["x1"],
            "y1": border_y + border["height"],
            "stroke_color": border_color,
            "fill_color": None,
            "width": 0.75,
        })

    total_h = footer_data["total_height"]
    return blocks, rects, total_h


def _get_footer_height(footer_data):
    """Get the total height needed for the footer content."""
    if not footer_data:
        return 0
    return footer_data["total_height"]


def _get_footer_gap(footer_data, profile):
    """Get the gap between last transaction and footer start."""
    if not footer_data:
        return profile.footer_gap
    return footer_data["gap_from_last_txn"]


# ── CSV parsing ─────────────────────────────────────────────────────────────

def _auto_fix_credit_debit(transactions):
    """Fix rows where Credit/Debit are in the wrong column."""
    if len(transactions) < 2:
        return transactions

    chrono = list(reversed(transactions))
    fixed_count = 0

    for i in range(1, len(chrono)):
        prev_bal = _parse_num(chrono[i - 1]["balance"])
        cur = chrono[i]
        credit = _parse_num(cur.get("credit", ""))
        debit = _parse_num(cur.get("debit", ""))
        actual_bal = _parse_num(cur["balance"])

        expected = round(prev_bal + credit - debit, 2)
        if abs(expected - actual_bal) <= 0.02:
            continue

        swapped = round(prev_bal + debit - credit, 2)
        if abs(swapped - actual_bal) <= 0.02:
            cur["credit"], cur["debit"] = cur["debit"], cur["credit"]
            fixed_count += 1

    if fixed_count:
        print(f"Auto-fixed credit/debit swap in {fixed_count} rows")

    return transactions


def parse_transactions_csv(csv_path):
    transactions = []
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            txn = {
                "date": row.get("Date", "").strip(),
                "description": row.get("Description", "").strip(),
                "credit": row.get("Credit", "").strip(),
                "debit": row.get("Debit", "").strip(),
                "balance": row.get("Balance", "").strip().replace('"', ''),
            }
            if txn["date"]:
                transactions.append(txn)
    _auto_fix_credit_debit(transactions)
    return transactions


# ── Main generation ─────────────────────────────────────────────────────────

def generate_pdf(template_path, data_path, csv_path, output_path, date_range_override=None):
    """Generate PDF using template structure + new data.

    All layout parameters come from the BankProfile embedded in the template.
    Falls back to DEFAULT_HSBC_PROFILE for templates without a profile key.
    """

    with open(template_path) as f:
        template = json.load(f)
    with open(data_path) as f:
        account = json.load(f)

    # Load profile (auto-detected or default HSBC)
    profile = _load_profile(template)

    transactions = parse_transactions_csv(csv_path)
    if not transactions:
        print("Error: no transactions found")
        return

    print(f"Loaded {len(transactions)} transactions")

    closing_balance = transactions[0].get("balance", "").replace(",", "").replace('"', '')
    if closing_balance:
        account["current_balance"] = closing_balance
        print(f"Header balance set to: {closing_balance}")

    if date_range_override:
        date_range = date_range_override
    else:
        dates = [txn["date"] for txn in transactions]
        date_range = (dates[-1], dates[0])

    page_w = template["page_width"]
    page_h = template["page_height"]
    image_dir = template.get("image_dir", "template_images")

    # Generate all content lines using profile
    content_items = _generate_all_text_lines(transactions, profile)

    # ── Flow engine: place content onto pages ──────────────────────────
    pages_data = []
    current_page = {"blocks": [], "rows": [], "table_top": profile.p1_table_top}

    current_y = profile.p1_first_content_y
    page_idx = 0
    last_type = None
    detail_count = 0
    detail_first_y = 0

    def _flush_detail_row():
        nonlocal detail_count, detail_first_y
        if detail_count > 0:
            h = detail_count * profile.detail_line_spacing + (profile.summary_to_detail_gap - profile.detail_line_spacing)
            current_page["rows"].append(("detail", detail_first_y, h))
            detail_count = 0

    def _new_page(first_y, item_type):
        nonlocal current_page, page_idx, current_y, last_type, detail_count, detail_first_y
        _flush_detail_row()
        pages_data.append(current_page)
        page_idx += 1
        current_page = {"blocks": [], "rows": [], "table_top": profile.cont_table_top}
        current_page["rows"].append(("header", profile.cont_header_text_y,
                                     profile.cont_first_content_y - profile.cont_header_text_y - 0.53))
        last_type = None
        detail_count = 0
        detail_first_y = 0
        current_y = first_y

    # Page 1: add header row
    current_page["rows"].append(("header", profile.p1_table_header_y,
                                 profile.p1_first_content_y - profile.p1_table_header_y - 0.53))

    for item in content_items:
        if item["type"] == "summary":
            if last_type == "detail":
                _flush_detail_row()
                next_y = current_y + profile.detail_to_next_summary
            elif last_type == "summary":
                next_y = current_y + profile.summary_row_height
            elif last_type is None:
                next_y = current_y
            else:
                next_y = current_y
        else:  # detail
            if last_type == "summary":
                next_y = current_y + profile.summary_to_detail_gap
            elif last_type == "detail":
                next_y = current_y + profile.detail_line_spacing
            elif last_type is None:
                next_y = current_y
            else:
                next_y = current_y

        # Check page overflow
        if next_y > profile.content_bottom:
            _new_page(profile.cont_first_content_y, item["type"])
            next_y = profile.cont_first_content_y

        # Place text blocks at next_y
        for block in item["blocks"]:
            b = copy.deepcopy(block)
            b["y"] = next_y
            b["y1"] = next_y + b["size"]
            current_page["blocks"].append(b)

        if item["type"] == "summary":
            current_page["rows"].append(("summary", next_y, profile.summary_row_height))
            detail_count = 0
        else:
            if detail_count == 0:
                detail_first_y = next_y
            detail_count += 1

        current_y = next_y
        last_type = item["type"]

    _flush_detail_row()
    pages_data.append(current_page)

    # ── Determine total pages with footer ────────────────────────────────
    footer_data = template.get("last_page_footer")
    footer_h = _get_footer_height(footer_data)
    footer_gap = _get_footer_gap(footer_data, profile)
    last_page_last_y = current_y
    footer_fits = (last_page_last_y + footer_gap + footer_h <= profile.content_bottom)
    total_pages = len(pages_data)
    if not footer_fits and footer_data:
        total_pages += 1

    print(f"Will generate {total_pages} pages")

    # ── Build final layout ─────────────────────────────────────────────
    layout = {"source": "template_builder", "pages": [], "image_dir": image_dir}

    for pi, pd in enumerate(pages_data):
        is_last_txn = (pi == len(pages_data) - 1)

        if pi == 0:
            header_blocks = _build_page1_header(account, date_range, total_pages, profile)
            all_blocks = header_blocks + pd["blocks"]

            grid_rects = _generate_grid_rects(pd["rows"], profile.p1_table_top, profile, is_last_txn)

            static_rects = [r for r in template["page1"].get("rects", [])
                           if r["y1"] < profile.p1_table_top]

            page = {
                "page": pi + 1,
                "width": page_w, "height": page_h,
                "text_blocks": all_blocks,
                "lines": [],
                "rects": static_rects + grid_rects,
                "images": template["page1"].get("images", []),
                "vector_regions": [vr for vr in template["page1"].get("vector_regions", [])
                                   if vr["y"] + vr["height"] < profile.p1_table_top],
            }
        else:
            header_blocks = _build_cont_page_header(
                pi + 1, total_pages,
                account.get("print_date", ""),
                account.get("print_time", ""),
                profile,
            )
            all_blocks = header_blocks + pd["blocks"]
            grid_rects = _generate_grid_rects(pd["rows"], profile.cont_table_top, profile, is_last_txn)

            page = {
                "page": pi + 1,
                "width": page_w, "height": page_h,
                "text_blocks": all_blocks,
                "lines": [],
                "rects": grid_rects,
                "images": [],
                "vector_regions": [],
            }

        is_last = (pi == len(pages_data) - 1)
        if is_last and footer_fits and footer_data:
            ftr_start = last_page_last_y + footer_gap
            ftr_blocks, ftr_rects, _ = _build_footer_from_template(ftr_start, footer_data)
            page["text_blocks"].extend(ftr_blocks)
            page["rects"].extend(ftr_rects)

        layout["pages"].append(page)

    # Separate footer page if needed
    if not footer_fits and footer_data:
        ftr_header = _build_cont_page_header(
            total_pages, total_pages,
            account.get("print_date", ""),
            account.get("print_time", ""),
            profile,
        )
        ftr_blocks, ftr_rects, _ = _build_footer_from_template(80.0, footer_data)
        layout["pages"].append({
            "page": total_pages,
            "width": page_w, "height": page_h,
            "text_blocks": ftr_header + ftr_blocks,
            "lines": [],
            "rects": ftr_rects,
            "images": [], "vector_regions": [],
        })

    print(f"Building PDF...")
    rebuild_pdf(layout, output_path)
    print(f"Done! → {output_path}")


def generate_sample_data(output_path):
    sample = {
        "customer_name": "MRS VARSHITHA N",
        "address_line_1": "38 3RD CROSS NEAR LIC CARE HOME",
        "address_line_2": "KUVEMPUNAGARA MADANAIYAKANAHALLI",
        "city_state": "BANGALORE RURAL KA I",
        "pin": "562123 562123",
        "account_number": "073-685745-006",
        "branch": "BANGALORE BRANCH",
        "micr": "560039002",
        "ifsc": "HSBC0560002",
        "nominee": "Yes",
        "account_type": "SAVINGS ACCOUNT - RES",
        "current_balance": "18,076.06",
        "overdraft": "0.00",
        "currency": "INR",
        "download_date": "27/03/2026",
        "print_date": "3/27/26",
        "print_time": "3:54 PM",
    }
    with open(output_path, "w") as f:
        json.dump(sample, f, indent=2)
    print(f"Sample account data → {output_path}")


# ── CLI ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PDF Template Builder")
    sub = parser.add_subparsers(dest="command")

    p1 = sub.add_parser("create-template")
    p1.add_argument("--pdf", required=True)
    p1.add_argument("--output", "-o", default="template.json")
    p1.add_argument("--image-dir", default="template_images")

    p2 = sub.add_parser("sample-data")
    p2.add_argument("--output", "-o", default="account_data.json")

    p3 = sub.add_parser("generate")
    p3.add_argument("--template", "-t", required=True)
    p3.add_argument("--data", "-d", required=True)
    p3.add_argument("--csv", "-c", required=True)
    p3.add_argument("--output", "-o", default="output.pdf")

    args = parser.parse_args()
    if args.command == "create-template":
        create_template(args.pdf, args.output, args.image_dir)
    elif args.command == "sample-data":
        generate_sample_data(args.output)
    elif args.command == "generate":
        generate_pdf(args.template, args.data, args.csv, args.output)
    else:
        parser.print_help()
