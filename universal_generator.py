"""
Universal PDF Statement Generator — Fully data-driven, zero bank-specific logic.

The profile JSON defines EVERYTHING: columns, CSV mapping, header layout,
grid patterns, fonts, colors, footer structure. This engine just reads and renders.

Supports two row models:
  - "flat": one row per transaction, variable height from text wrapping (HDFC style)
  - "two_tier": summary row + detail sub-rows (HSBC style)

Usage:
    from universal_generator import generate_pdf
    generate_pdf(profile, template_path, account_data_path, csv_path, output_path)
"""

import copy
import csv
import json
import os
import re
from datetime import datetime

from reportlab.pdfbase.pdfmetrics import stringWidth
from pdf_rebuilder import rebuild_pdf, map_font, _register_ttf_fonts

_register_ttf_fonts()


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _tb(text, x, y, font_spec, x1=None):
    """Create a text block dict."""
    return {
        "text": str(text), "x": x, "y": y,
        "x1": x1 or (x + len(str(text)) * font_spec["size"] * 0.5),
        "y1": y + font_spec["size"],
        "font": font_spec["font"], "size": font_spec["size"], "color": font_spec["color"],
    }


def _right_x(text, right_edge, font_spec):
    """Calculate X for right-aligned text."""
    w = stringWidth(text, map_font(font_spec["font"]), font_spec["size"])
    return right_edge - w


def _parse_num(value):
    if not value:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace(",", "").replace('"', '').strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _fmt_amt(value, fmt=None):
    """Format amount with commas and decimals."""
    if isinstance(value, str):
        value = _parse_num(value)
    places = (fmt or {}).get("decimal_places", 2)
    prefix = (fmt or {}).get("prefix", " ")
    return f"{prefix}{value:,.{places}f}"


def _fmt_date(date_str, out_fmt=None):
    """Normalize date format."""
    if not date_str:
        return ""
    parts = date_str.strip().split("/")
    if len(parts) == 3 and len(parts[2]) == 2:
        return f"{parts[0]}/{parts[1]}/{2000 + int(parts[2])}"
    return date_str


def _get_font(profile, role_or_spec):
    """Get font spec from profile by role name, or return the spec directly."""
    if isinstance(role_or_spec, dict):
        return role_or_spec
    fonts = profile.get("fonts", {})
    return fonts.get(role_or_spec, {"font": "ArialMT", "size": 8.0, "color": "#000000"})


def _wrap_text(text, max_width, font_spec):
    """Word-wrap text to fit within max_width using actual font metrics."""
    if not text or max_width <= 0:
        return [text or ""]
    font_name = map_font(font_spec["font"])
    font_size = font_spec["size"]

    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        w = stringWidth(test, font_name, font_size)
        if w <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    return lines or [""]


# ══════════════════════════════════════════════════════════════════════════════
# V1 → V2 PROFILE CONVERSION
# ══════════════════════════════════════════════════════════════════════════════

def _convert_v1_to_v2(v1):
    """Convert old BankProfile dict (v1) to universal profile dict (v2)."""
    columns = v1.get("columns", [])
    table_columns = []
    for col in columns:
        tc = {
            "name": col.get("name", ""),
            "role": col.get("role", ""),
            "text_x": col.get("x", 0),
            "x0": col.get("x", 0) - 10 if col.get("align") == "left" else col.get("x", 0) - 100,
            "x1": col.get("x1", col.get("x", 0) + 100),
            "align": col.get("align", "left"),
            "header_x": col.get("header_x", col.get("x", 0)),
            "header_font": "table_header",
            "cell_font": "transaction",
            "wrap": col.get("role") == "description",
            "max_width_pt": 180 if col.get("role") == "description" else None,
        }
        if col.get("align") == "right":
            tc["right_edge"] = col.get("x", 0)
        table_columns.append(tc)

    return {
        "_schema_version": "2.0",
        "page": {"width": v1.get("page_width", 594.96), "height": v1.get("page_height", 841.92)},
        "fonts": v1.get("fonts", {}),
        "csv_mapping": {
            "columns": [
                {"csv_header": "Date", "role": "date"},
                {"csv_header": "Description", "role": "description"},
                {"csv_header": "Credit", "role": "credit", "type": "amount"},
                {"csv_header": "Debit", "role": "debit", "type": "amount"},
                {"csv_header": "Balance", "role": "balance", "type": "amount"},
            ],
            "amount_format": {"decimal_places": 2, "prefix": " "},
        },
        "table": {
            "columns": table_columns,
            "row_model": "two_tier",
            "two_tier_config": {
                "description_split": " - ",
                "summary_row_height": v1.get("summary_row_height", 32.5),
                "detail_line_spacing": v1.get("detail_line_spacing", 16.0),
                "summary_to_detail_gap": v1.get("summary_to_detail_gap", 32.5),
                "detail_to_next_summary": v1.get("detail_to_next_summary", 37.8),
                "detail_x": next((c["x"] for c in columns if c.get("role") == "description"), 138.3),
            },
            "text_to_border_gap": v1.get("text_to_border_gap", 11.45),
            "grid_colors": v1.get("grid_colors", {"border": [0.8, 0.8, 0.8], "separator": [0.87, 0.89, 0.90]}),
            "col_bounds": v1.get("col_bounds", []),
            "closing_col_segments": v1.get("closing_col_segments", []),
            "rect_patterns": {
                "header": v1.get("header_row_rects_pattern", []),
                "data_row": v1.get("summary_row_rects_pattern", []),
                "detail_row": v1.get("detail_row_rects_pattern", []),
            },
        },
        "page1": {
            "header_regions": v1.get("header_fields", []),
            "table_header_y": v1.get("p1_table_header_y", 399.2),
            "first_content_y": v1.get("p1_first_content_y", 427.6),
            "table_top": v1.get("p1_table_top", 389.1),
            "content_bottom": v1.get("content_bottom", 729.0),
        },
        "continuation_page": {
            "header_regions": [
                {"type": "text", "role": "__chrome__", "x": 24.0,
                 "y": v1.get("browser_chrome", {}).get("top_y", 15.9),
                 "font": "browser_chrome", "template": "{print_date}, {print_time}"},
                {"type": "text", "role": "__chrome__", "x": 280.6,
                 "y": v1.get("browser_chrome", {}).get("top_y", 15.9),
                 "font": "browser_chrome",
                 "template": v1.get("browser_chrome", {}).get("title_text", "")},
            ],
            "table_header_y": v1.get("cont_header_text_y", 52.8),
            "table_header_columns": [c.get("role") for c in v1.get("cont_header_fields", [])
                                     ] or ["balance"],
            "first_content_y": v1.get("cont_first_content_y", 81.8),
            "table_top": v1.get("cont_table_top", 42.75),
            "content_bottom": v1.get("content_bottom", 729.0),
        },
        "footer": {
            "per_page_fields": [
                {"type": "text", "role": "__chrome__",
                 "x": 24.0, "y": v1.get("footer_y", 819.1),
                 "font": "browser_chrome",
                 "template": v1.get("browser_chrome", {}).get("url_text", "about:blank")},
                {"type": "text", "role": "__chrome__",
                 "x": v1.get("browser_chrome", {}).get("page_num_x", 551.2),
                 "y": v1.get("footer_y", 819.1),
                 "font": "browser_chrome",
                 "template": "{page_num}/{total_pages}"},
            ],
            "gap_from_last_txn": v1.get("footer_gap", 49.0),
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# CSV PARSING
# ══════════════════════════════════════════════════════════════════════════════

def _parse_csv(csv_path, profile):
    """Parse any CSV using the profile's csv_mapping."""
    csv_mapping = profile.get("csv_mapping", {})
    mapping_cols = csv_mapping.get("columns", [])

    transactions = []
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        csv_headers = reader.fieldnames or []

        # Build header → role map
        header_to_role = {}
        for mc in mapping_cols:
            csv_header = mc.get("csv_header", "")
            role = mc.get("role", "")
            # Try exact match first
            if csv_header in csv_headers:
                header_to_role[csv_header] = role

        # Fallback: if no mapping, use default column names
        if not header_to_role:
            defaults = {"Date": "date", "Description": "description", "Narration": "description",
                        "Credit": "credit", "Debit": "debit", "Balance": "balance",
                        "Withdrawal Amt.": "debit", "Deposit Amt.": "credit",
                        "Closing Balance": "balance", "Chq./Ref.No.": "ref",
                        "Value Dt": "value_date"}
            for h in csv_headers:
                if h in defaults:
                    header_to_role[h] = defaults[h]

        for row in reader:
            txn = {}
            for header, role in header_to_role.items():
                val = row.get(header, "").strip()
                if role in txn and txn[role]:
                    continue  # Don't overwrite existing mapping
                txn[role] = val
            if txn.get("date"):
                transactions.append(txn)

    return transactions


# ══════════════════════════════════════════════════════════════════════════════
# AUTO-FIX CREDIT/DEBIT
# ══════════════════════════════════════════════════════════════════════════════

def _auto_fix_credit_debit(transactions):
    """Fix rows where credit/debit are in the wrong column.

    Walks chronologically and checks each row's balance against the previous.
    """
    if len(transactions) < 2:
        return

    chrono = list(reversed(transactions))
    fixed = 0

    for i in range(1, len(chrono)):
        prev_bal = _parse_num(chrono[i - 1].get("balance", ""))
        cur = chrono[i]
        credit = _parse_num(cur.get("credit", ""))
        debit = _parse_num(cur.get("debit", ""))
        actual_bal = _parse_num(cur.get("balance", ""))

        expected = round(prev_bal + credit - debit, 2)
        if abs(expected - actual_bal) <= 0.02:
            continue

        swapped = round(prev_bal + debit - credit, 2)
        if abs(swapped - actual_bal) <= 0.02:
            cur["credit"], cur["debit"] = cur["debit"], cur["credit"]
            fixed += 1

    if fixed:
        print(f"Auto-fixed credit/debit swap in {fixed} rows")


# ══════════════════════════════════════════════════════════════════════════════
# ROW BUILDING
# ══════════════════════════════════════════════════════════════════════════════

def _build_rows(transactions, profile):
    """Convert transactions into renderable rows based on the row_model."""
    table = profile.get("table", {})
    columns = table.get("columns", [])
    row_model = table.get("row_model", "flat")
    amt_fmt = profile.get("csv_mapping", {}).get("amount_format", {})

    rows = []

    for txn in transactions:
        if row_model == "two_tier":
            rows.extend(_build_two_tier_rows(txn, columns, table, profile, amt_fmt))
        else:
            rows.extend(_build_flat_rows(txn, columns, table, profile, amt_fmt))

    return rows


def _build_flat_rows(txn, columns, table, profile, amt_fmt):
    """Build flat rows — one row per transaction, variable height from wrapping."""
    flat_cfg = table.get("flat_config", {})
    line_height = flat_cfg.get("line_height", 10.0)
    padding_top = flat_cfg.get("row_padding_top", 4.0)
    padding_bottom = flat_cfg.get("row_padding_bottom", 4.0)

    # For each column, get the text and optionally wrap
    col_lines = {}  # column role → list of text lines
    max_lines = 1

    for col in columns:
        role = col.get("role", "")
        raw = txn.get(role, "")

        # Format amounts
        if col.get("type") == "amount" or role in ("credit", "debit", "balance"):
            val = _parse_num(raw)
            if val > 0:
                text = _fmt_amt(val, amt_fmt)
            elif role == "balance":
                text = _fmt_amt(val, amt_fmt)
            else:
                text = ""
        elif role == "date":
            text = _fmt_date(raw)
        else:
            text = raw

        # Wrap if needed
        if col.get("wrap") and text:
            max_w = col.get("max_width_pt") or (col.get("x1", 0) - col.get("x0", 0) - 5)
            font = _get_font(profile, col.get("cell_font", "transaction"))
            lines = _wrap_text(text, max_w, font)
        else:
            lines = [text] if text else [""]

        col_lines[role] = lines
        max_lines = max(max_lines, len(lines))

    # Calculate row height
    row_height = padding_top + max_lines * line_height + padding_bottom

    # Build text blocks for each line of each column
    blocks = []
    for col in columns:
        role = col.get("role", "")
        lines = col_lines.get(role, [""])
        font = _get_font(profile, col.get("cell_font", "transaction"))
        align = col.get("align", "left")

        for line_idx, line_text in enumerate(lines):
            if not line_text:
                continue
            # Y offset within the row (set to 0, will be adjusted during pagination)
            y_in_row = padding_top + line_idx * line_height

            if align == "right":
                right_edge = col.get("right_edge", col.get("text_x", col.get("x1", 0)))
                x = _right_x(line_text, right_edge, font)
            else:
                x = col.get("text_x", col.get("x0", 0))

            blocks.append({
                "text": line_text, "x": x, "y_in_row": y_in_row,
                "font": font["font"], "size": font["size"], "color": font["color"],
            })

    return [{"type": "data_row", "blocks": blocks, "height": row_height}]


def _build_two_tier_rows(txn, columns, table, profile, amt_fmt):
    """Build two-tier rows — summary row + detail sub-rows (HSBC style)."""
    cfg = table.get("two_tier_config", {})
    split_char = cfg.get("description_split", " - ")
    summary_height = cfg.get("summary_row_height", 32.5)
    detail_spacing = cfg.get("detail_line_spacing", 16.0)

    desc = txn.get("description", "")
    if split_char and split_char in desc:
        desc_parts = desc.split(split_char, 1) if split_char == " - " else desc.split(split_char)
    else:
        desc_parts = [desc]
    txn_type = desc_parts[0].strip() if desc_parts else ""

    # Summary row: date + type + amounts
    summary_blocks = []
    for col in columns:
        role = col.get("role", "")
        font = _get_font(profile, col.get("cell_font", "transaction"))
        align = col.get("align", "left")

        if role == "date":
            text = _fmt_date(txn.get("date", ""))
        elif role == "description":
            text = txn_type
        elif role in ("credit", "debit"):
            val = _parse_num(txn.get(role, ""))
            text = _fmt_amt(val, amt_fmt) if val > 0 else ""
        elif role == "balance":
            text = _fmt_amt(txn.get("balance", ""), amt_fmt)
        else:
            text = txn.get(role, "")

        if not text:
            continue

        if align == "right":
            right_edge = col.get("right_edge", col.get("text_x", col.get("x1", 0)))
            x = _right_x(text, right_edge, font)
        else:
            x = col.get("text_x", col.get("x0", 0))

        summary_blocks.append(_tb(text, x, 0, font))

    rows = [{"type": "data_row", "blocks": summary_blocks, "height": summary_height}]

    # Detail rows: description parts
    desc_col = next((c for c in columns if c.get("role") == "description"), None)
    detail_x = cfg.get("detail_x", desc_col["text_x"] if desc_col else 138.0)
    detail_font = _get_font(profile, (desc_col or {}).get("cell_font", "transaction"))

    for part in desc_parts:
        rows.append({
            "type": "detail_row",
            "blocks": [_tb(part.strip(), detail_x, 0, detail_font)],
            "height": detail_spacing,
        })

    return rows


# ══════════════════════════════════════════════════════════════════════════════
# PAGINATION
# ══════════════════════════════════════════════════════════════════════════════

def _paginate(rows, profile):
    """Flow rows onto pages, handling page breaks."""
    p1 = profile.get("page1", {})
    cont = profile.get("continuation_page", {})
    table = profile.get("table", {})
    row_model = table.get("row_model", "flat")

    pages = [{"rows": [], "table_top": p1.get("table_top", 389.1), "is_first": True}]

    current_y = p1.get("first_content_y", 427.6)
    content_bottom = p1.get("content_bottom", 729.0)

    # Add table header marker for page 1
    header_y = p1.get("table_header_y", current_y - 28)
    if header_y:
        header_height = current_y - header_y - 0.53
        pages[0]["rows"].append({"type": "header", "y": header_y, "height": max(header_height, 10)})

    last_type = None

    for row in rows:
        # Calculate spacing based on row model
        if row_model == "two_tier":
            cfg = table.get("two_tier_config", {})
            if row["type"] == "data_row":
                if last_type == "detail_row":
                    spacing = cfg.get("detail_to_next_summary", 37.8)
                elif last_type == "data_row":
                    spacing = cfg.get("summary_row_height", 32.5)
                else:
                    spacing = 0
            else:  # detail_row
                if last_type == "data_row":
                    spacing = cfg.get("summary_to_detail_gap", 32.5)
                elif last_type == "detail_row":
                    spacing = cfg.get("detail_line_spacing", 16.0)
                else:
                    spacing = 0
        else:
            # Flat model: just use row height
            spacing = 0 if last_type is None else 0  # rows are self-contained with height

        next_y = current_y + spacing if last_type is not None else current_y

        # Check page overflow
        if next_y + row["height"] > content_bottom:
            pages.append({
                "rows": [],
                "table_top": cont.get("table_top", 42.75),
                "is_first": False,
            })
            current_y = cont.get("first_content_y", 81.8)
            content_bottom = cont.get("content_bottom", 729.0)
            next_y = current_y

            # Add header for continuation page
            cont_header_y = cont.get("table_header_y")
            if cont_header_y:
                h = current_y - cont_header_y - 0.53
                pages[-1]["rows"].append({"type": "header", "y": cont_header_y, "height": max(h, 10)})

        # Set Y on all blocks
        for block in row.get("blocks", []):
            if "y_in_row" in block:
                block["y"] = next_y + block.pop("y_in_row")
            else:
                block["y"] = next_y
                block["y1"] = next_y + block.get("size", 8)

        row["y"] = next_y
        pages[-1]["rows"].append(row)

        if row_model == "flat":
            current_y = next_y + row["height"]
        else:
            current_y = next_y

        last_type = row["type"]

    return pages


# ══════════════════════════════════════════════════════════════════════════════
# REGION RENDERING
# ══════════════════════════════════════════════════════════════════════════════

def _render_regions(regions, profile, account_data, page_num=1, total_pages=1):
    """Render header/footer regions by substituting {placeholders}."""
    blocks = []
    rects = []

    for region in regions:
        rtype = region.get("type", "text")

        if rtype == "text":
            template = region.get("template", "")
            text = template

            # Substitute account data placeholders
            for key, value in account_data.items():
                placeholder = "{" + key + "}"
                if placeholder in text:
                    if "balance" in key:
                        text = text.replace(placeholder, _fmt_amt(value))
                    elif "date" in key:
                        text = text.replace(placeholder, _fmt_date(str(value)))
                    else:
                        text = text.replace(placeholder, str(value))

            text = text.replace("{page_num}", str(page_num))
            text = text.replace("{total_pages}", str(total_pages))

            # Skip unresolved placeholders
            if re.search(r'\{[a-z_]+\}', text):
                continue

            # Support both v2 "font" key and v1 "font_key" and "original_font"
            if "original_font" in region:
                font = region["original_font"]
            else:
                font = _get_font(profile, region.get("font", region.get("font_key", "transaction")))
            align = region.get("align", "left")

            if align == "right":
                x = _right_x(text, region["x"], font)
            else:
                x = region["x"]

            blocks.append(_tb(text, x, region["y"], font))

        elif rtype == "rect":
            rects.append({
                "x0": region["x0"], "y0": region["y0"],
                "x1": region["x1"], "y1": region["y1"],
                "stroke_color": region.get("stroke_color"),
                "fill_color": region.get("fill_color"),
                "width": region.get("width", 0.75),
            })

    return blocks, rects


def _render_table_header(columns, header_y, profile, which_columns=None):
    """Render table column headers."""
    blocks = []
    for col in columns:
        role = col.get("role", "")
        if which_columns and role not in which_columns and "all" not in which_columns:
            continue

        font = _get_font(profile, col.get("header_font", "table_header"))
        x = col.get("header_x", col.get("text_x", col.get("x0", 0)))
        blocks.append(_tb(col["name"], x, header_y, font))

    return blocks


# ══════════════════════════════════════════════════════════════════════════════
# GRID RECT STAMPING
# ══════════════════════════════════════════════════════════════════════════════

def _stamp_grid_rects(page_rows, profile):
    """Stamp rect patterns for each row."""
    table = profile.get("table", {})
    patterns = table.get("rect_patterns", {})
    gap = table.get("text_to_border_gap", 11.45)
    col_bounds = table.get("col_bounds", [])

    rects = []

    for row in page_rows:
        row_type = row.get("type", "data_row")
        if row_type == "header":
            pattern = patterns.get("header", [])
        elif row_type == "detail_row":
            pattern = patterns.get("detail_row", patterns.get("data_row", []))
        else:
            pattern = patterns.get("data_row", [])

        if not pattern:
            continue

        text_y = row.get("y", 0)
        row_height = row.get("height", 20)
        border_y = text_y - gap

        for pr in pattern:
            if pr.get("at_row_bottom"):
                y0 = border_y + row_height + pr.get("y_offset_from_bottom", 0)
            else:
                y0 = border_y + pr.get("y_offset", 0)

            if pr.get("use_row_height"):
                h = row_height - pr.get("y_offset", 0)
            else:
                h = pr.get("height", 0.53)

            rects.append({
                "x0": pr["x0"], "x1": pr["x1"],
                "y0": y0, "y1": y0 + h,
                "fill_color": pr.get("fill_color"),
                "stroke_color": pr.get("stroke_color"),
                "width": pr.get("width", 0.75),
            })

    # Outer table background
    data_rows = [r for r in page_rows if r.get("y")]
    if data_rows and col_bounds:
        first_y = min(r["y"] for r in data_rows) - gap
        last_r = max(data_rows, key=lambda r: r["y"])
        last_y = last_r["y"] - gap + last_r.get("height", 20)
        rects.insert(0, {
            "x0": col_bounds[0], "x1": col_bounds[-1],
            "y0": first_y, "y1": last_y + 1,
            "fill_color": [1, 1, 1], "stroke_color": [1, 1, 1], "width": 0.75,
        })

    return rects


# ══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════════════

def _build_footer_from_template(start_y, footer_data):
    """Build footer blocks from extracted template footer data."""
    if not footer_data:
        return [], [], 0
    blocks = []
    rects = []
    for span in footer_data.get("spans", []):
        y = start_y + span.get("y_offset", 0)
        font_spec = {"font": span.get("font", "ArialMT"), "size": span["size"], "color": span["color"]}
        b = _tb(span["text"], span["x"], y, font_spec)
        if span.get("link"):
            b["link"] = span["link"]
        blocks.append(b)
    border = footer_data.get("border")
    if border:
        by = start_y + border.get("y_offset", 0)
        rects.append({
            "x0": border["x0"], "y0": by, "x1": border["x1"], "y1": by + border.get("height", 100),
            "stroke_color": border.get("color", [0.2, 0.2, 0.2]), "fill_color": None, "width": 0.75,
        })
    return blocks, rects, footer_data.get("total_height", 0)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN GENERATION
# ══════════════════════════════════════════════════════════════════════════════

def generate_pdf(template_path, account_data_path, csv_path, output_path,
                 date_range_override=None, profile_override=None):
    """Generate PDF from profile + template + account data + CSV.

    Fully dynamic — reads everything from the profile.
    """
    with open(template_path) as f:
        template = json.load(f)
    with open(account_data_path) as f:
        account_data = json.load(f)

    # Load profile from template or override
    if profile_override:
        profile = profile_override
    else:
        profile = template.get("profile", {})

    if not profile:
        # Fallback: convert old BankProfile defaults to v2 profile format
        from bank_profile import DEFAULT_HSBC_PROFILE
        p = DEFAULT_HSBC_PROFILE
        profile = _convert_v1_to_v2(p.to_dict())
        print("Using DEFAULT_HSBC_PROFILE (legacy fallback)")

    # If profile has old v1 keys (columns at top level, no "table" key), convert
    if "columns" in profile and "table" not in profile:
        profile = _convert_v1_to_v2(profile)
        print("Converted v1 profile to v2 format")

    # Parse CSV
    transactions = _parse_csv(csv_path, profile)
    if not transactions:
        print("Error: no transactions found")
        return

    print(f"Loaded {len(transactions)} transactions")

    # Auto-fix credit/debit swaps
    _auto_fix_credit_debit(transactions)

    # Update account balance from newest transaction
    if transactions and transactions[0].get("balance"):
        bal = transactions[0]["balance"].replace(",", "").replace('"', '')
        if bal:
            account_data["current_balance"] = bal
            print(f"Header balance set to: {bal}")

    # Date range
    if date_range_override:
        date_range = date_range_override
    else:
        dates = [t.get("date", "") for t in transactions if t.get("date")]
        date_range = (dates[-1], dates[0]) if dates else None

    if date_range:
        account_data["_date_range_start"] = _fmt_date(date_range[0])
        account_data["_date_range_end"] = _fmt_date(date_range[1])

    # Add date range rendering to page1 header regions if not already present
    p1 = profile.get("page1", {})
    regions = p1.get("header_regions", [])
    has_date_range = any("date_range" in r.get("template", "") or
                         r.get("role") == "date_range" for r in regions)
    if not has_date_range and date_range:
        # Find "Search results" heading Y to place date range below it
        heading_y = 348.3
        for r in regions:
            if r.get("template") == "Search results":
                heading_y = r.get("y", 348.3)
                break
        dr_y = heading_y + 17.4
        label_font = profile.get("fonts", {}).get("label", {"font": "ArialMT", "size": 7.45, "color": "#666666"})
        name_font = profile.get("fonts", {}).get("name", {"font": "ArialMT", "size": 7.45, "color": "#212529"})
        start_str = _fmt_date(date_range[0])
        end_str = _fmt_date(date_range[1])

        # Calculate X positions for date range text
        start_x = 87.0
        start_w = stringWidth(start_str, map_font(name_font["font"]), name_font["size"])
        dash_x = start_x + start_w + 4
        dash_w = stringWidth(" - ", map_font(name_font["font"]), name_font["size"])
        end_x = dash_x + dash_w

        # Inject date range fields into header regions
        regions.extend([
            {"type": "text", "x": 42.8, "y": dr_y, "font": "label", "template": "Date range:"},
            {"type": "text", "x": start_x, "y": dr_y, "font": "name", "template": start_str},
            {"type": "text", "x": dash_x, "y": dr_y, "font": "name", "template": "-"},
            {"type": "text", "x": end_x, "y": dr_y, "font": "name", "template": end_str},
        ])

    # Build rows
    rows = _build_rows(transactions, profile)

    # Paginate
    pages = _paginate(rows, profile)

    # Determine footer
    footer_data = template.get("last_page_footer")
    footer_cfg = profile.get("footer", {})
    footer_gap = footer_cfg.get("gap_from_last_txn",
                                footer_data.get("gap_from_last_txn", 49.0) if footer_data else 49.0)
    footer_h = footer_data.get("total_height", 0) if footer_data else 0

    # Check if footer fits on last page
    last_page = pages[-1] if pages else None
    last_y = 0
    if last_page:
        data_rows = [r for r in last_page["rows"] if r.get("y")]
        if data_rows:
            lr = max(data_rows, key=lambda r: r["y"])
            last_y = lr["y"] + lr.get("height", 20)

    content_bottom = profile.get("continuation_page", {}).get("content_bottom",
                     profile.get("page1", {}).get("content_bottom", 729.0))
    footer_fits = (last_y + footer_gap + footer_h <= content_bottom)

    total_pages = len(pages)
    if footer_data and not footer_fits:
        total_pages += 1

    print(f"Will generate {total_pages} pages")

    # Build layout
    page_w = profile.get("page", {}).get("width", template.get("page_width", 594.96))
    page_h = profile.get("page", {}).get("height", template.get("page_height", 841.92))
    image_dir = template.get("image_dir", "template_images")

    layout = {"source": "universal_generator", "pages": [], "image_dir": image_dir}

    for pi, page in enumerate(pages):
        is_first = page.get("is_first", pi == 0)
        is_last_txn = (pi == len(pages) - 1)

        if is_first:
            page_cfg = profile.get("page1", {})
            regions = page_cfg.get("header_regions", [])
            header_blocks, header_rects = _render_regions(
                regions, profile, account_data, pi + 1, total_pages)
            table_header_blocks = _render_table_header(
                profile.get("table", {}).get("columns", []),
                page_cfg.get("table_header_y", 399.2),
                profile)

            # Static elements from template page 1
            table_top = page_cfg.get("table_top", 389.1)
            static_rects = [r for r in template.get("page1", {}).get("rects", [])
                           if r.get("y1", 999) < table_top]
            static_images = template.get("page1", {}).get("images", [])
            static_vectors = [vr for vr in template.get("page1", {}).get("vector_regions", [])
                             if vr.get("y", 0) + vr.get("height", 0) < table_top]
        else:
            page_cfg = profile.get("continuation_page", {})
            regions = page_cfg.get("header_regions", [])
            header_blocks, header_rects = _render_regions(
                regions, profile, account_data, pi + 1, total_pages)

            # Continuation table header
            cont_header_y = page_cfg.get("table_header_y")
            which = page_cfg.get("table_header_columns")
            if cont_header_y and which:
                table_header_blocks = _render_table_header(
                    profile.get("table", {}).get("columns", []),
                    cont_header_y, profile, which)
            elif cont_header_y:
                table_header_blocks = _render_table_header(
                    profile.get("table", {}).get("columns", []),
                    cont_header_y, profile)
            else:
                table_header_blocks = []

            static_rects = []
            static_images = []
            static_vectors = []

        # Row text blocks
        row_blocks = []
        for row in page["rows"]:
            for block in row.get("blocks", []):
                row_blocks.append(block)

        # Grid rects
        grid_rects = _stamp_grid_rects(page["rows"], profile)

        # Per-page footer
        footer_blocks = []
        per_page = footer_cfg.get("per_page_fields", [])
        if per_page:
            fb, fr = _render_regions(per_page, profile, account_data, pi + 1, total_pages)
            footer_blocks = fb
            header_rects.extend(fr)

        layout_page = {
            "page": pi + 1,
            "width": page_w, "height": page_h,
            "text_blocks": header_blocks + table_header_blocks + row_blocks + footer_blocks,
            "rects": static_rects + header_rects + grid_rects,
            "lines": [],
            "images": static_images,
            "vector_regions": static_vectors,
        }

        # Last page disclaimer
        if is_last_txn and footer_fits and footer_data:
            ftr_start = last_y + footer_gap
            ftr_blocks, ftr_rects, _ = _build_footer_from_template(ftr_start, footer_data)
            layout_page["text_blocks"].extend(ftr_blocks)
            layout_page["rects"].extend(ftr_rects)

        layout["pages"].append(layout_page)

    # Separate footer page if needed
    if footer_data and not footer_fits:
        cont_cfg = profile.get("continuation_page", {})
        regions = cont_cfg.get("header_regions", [])
        ftr_header, ftr_header_rects = _render_regions(
            regions, profile, account_data, total_pages, total_pages)
        ftr_blocks, ftr_rects, _ = _build_footer_from_template(80.0, footer_data)

        per_page = footer_cfg.get("per_page_fields", [])
        ftr_footer = []
        if per_page:
            fb, _ = _render_regions(per_page, profile, account_data, total_pages, total_pages)
            ftr_footer = fb

        layout["pages"].append({
            "page": total_pages,
            "width": page_w, "height": page_h,
            "text_blocks": ftr_header + ftr_blocks + ftr_footer,
            "rects": ftr_header_rects + ftr_rects,
            "lines": [], "images": [], "vector_regions": [],
        })

    print(f"Building PDF...")
    rebuild_pdf(layout, output_path)
    print(f"Done! → {output_path}")


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Universal PDF Statement Generator")
    parser.add_argument("--template", "-t", required=True)
    parser.add_argument("--account", "-a", required=True)
    parser.add_argument("--csv", "-c", required=True)
    parser.add_argument("--output", "-o", default="output.pdf")
    args = parser.parse_args()
    generate_pdf(args.template, args.account, args.csv, args.output)
