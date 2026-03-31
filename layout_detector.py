"""
Layout Detector — Auto-detect table structure, columns, fonts, spacing, header/footer
from any bank statement PDF using the output of pdf_analyzer.py.

Produces a BankProfile that captures all layout parameters needed to generate new PDFs.

Usage:
    from layout_detector import detect_layout
    from pdf_analyzer import analyze_pdf

    layout = analyze_pdf("statement.pdf", pages=[1, 2])
    profile = detect_layout(layout)
"""

from collections import Counter
from bank_profile import BankProfile, _normalize_column_name


# ── Table keyword sets ────────────────────────────────────────────────────────

TABLE_KEYWORDS = {
    "date", "txn date", "transaction date", "value date", "val date", "posting date",
    "description", "particulars", "narration", "details", "transaction details",
    "remark", "remarks",
    "credit", "deposit", "cr", "credits", "deposits",
    "debit", "withdrawal", "dr", "debits", "withdrawals",
    "balance", "closing balance", "running balance", "bal",
    "amount", "amt",
    "cheque", "chq", "chq no", "cheque no", "ref", "ref no", "reference",
}

NUMERIC_ROLES = {"credit", "debit", "balance", "amount", "cheque"}


# ── Clustering helpers ────────────────────────────────────────────────────────

def _cluster_by_y(blocks, tolerance=3.0):
    """Group blocks by Y position within tolerance. Returns list of clusters."""
    if not blocks:
        return []
    sorted_blocks = sorted(blocks, key=lambda b: b["y"])
    clusters = []
    current = [sorted_blocks[0]]

    for b in sorted_blocks[1:]:
        if abs(b["y"] - current[0]["y"]) <= tolerance:
            current.append(b)
        else:
            clusters.append(current)
            current = [b]
    clusters.append(current)
    return clusters


def _most_common(values):
    """Return the most common value in a list."""
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def _median(values):
    """Return median of a list of numbers."""
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2


# ── Core detection ────────────────────────────────────────────────────────────

def _detect_table_header(page_data):
    """Find the transaction table header row on a page.

    Scans text blocks for known table keywords, clusters matches by Y,
    and returns the cluster with the most keyword matches.

    Returns: (header_blocks, header_y) or (None, None)
    """
    text_blocks = page_data.get("text_blocks", [])
    candidates = []

    for block in text_blocks:
        text_lower = block["text"].strip().lower()
        if text_lower in TABLE_KEYWORDS:
            candidates.append(block)

    if not candidates:
        # Try multi-word matching (e.g., "Txn Date" as two separate blocks)
        return None, None

    clusters = _cluster_by_y(candidates, tolerance=3.0)

    # The header row is the cluster with the most keyword matches
    best_cluster = max(clusters, key=len)

    if len(best_cluster) < 2:
        # Need at least 2 matches to be a table header
        return None, None

    header_y = round(sum(b["y"] for b in best_cluster) / len(best_cluster), 2)
    return best_cluster, header_y


def _detect_columns(header_blocks):
    """Extract column definitions from the detected header row blocks.

    Returns: list of column dicts with name, role, x, x1, align, header_x, font.
    """
    columns = []
    for block in sorted(header_blocks, key=lambda b: b["x"]):
        name = block["text"].strip()
        role = _normalize_column_name(name)
        align = "right" if role in NUMERIC_ROLES else "left"
        font = {"font": block["font"], "size": block["size"], "color": block["color"]}

        columns.append({
            "name": name,
            "role": role,
            "x": round(block["x"], 1) if align == "left" else round(block["x1"], 1),
            "x1": round(block["x1"], 1),
            "align": align,
            "header_x": round(block["x"], 1),
            "font": font,
        })

    return columns


def _detect_col_bounds(page_data, header_y, page_width):
    """Detect column boundaries from table grid rects.

    Looks for vertical edges in rects near the header Y.
    Falls back to inferring from column positions if no grid rects exist.

    Returns: sorted list of X boundaries.
    """
    rects = page_data.get("rects", [])

    # Find rects near the table header
    table_rects = [r for r in rects if abs(r["y0"] - header_y) < 30 or abs(r["y1"] - header_y) < 30]

    if not table_rects:
        # Look for rects in a wider range below header
        table_rects = [r for r in rects if header_y - 20 < r["y0"] < header_y + 200]

    if table_rects:
        # Collect all unique X edges from rects
        x_edges = set()
        for r in table_rects:
            x_edges.add(round(r["x0"], 1))
            x_edges.add(round(r["x1"], 1))

        # Filter to reasonable page range and sort
        x_edges = sorted(e for e in x_edges if 20 < e < page_width - 20)

        if len(x_edges) >= 3:
            return x_edges

    return []


def _detect_table_top(page_data, header_y):
    """Find the top edge of the table (topmost rect/line near header).

    Returns: table_top Y position.
    """
    rects = page_data.get("rects", [])

    # Look for horizontal rects just above the header text
    candidates = []
    for r in rects:
        # Rect should span a good portion of the page (>200pt wide)
        width = r["x1"] - r["x0"]
        if width > 200 and header_y - 30 < r["y0"] < header_y:
            candidates.append(r["y0"])

    if candidates:
        return round(min(candidates), 2)

    # Fallback: estimate from header Y
    return round(header_y - 10, 2)


def _detect_first_content_y(page_data, header_y, transaction_font):
    """Find the Y of the first transaction text below the header.

    Returns: first_content_y.
    """
    text_blocks = page_data.get("text_blocks", [])

    # Find first text block below header with the transaction font
    candidates = []
    for b in text_blocks:
        if b["y"] > header_y + 5:
            # Match by font size (within 1pt tolerance)
            if transaction_font and abs(b["size"] - transaction_font["size"]) < 1.0:
                candidates.append(b["y"])

    if candidates:
        return round(min(candidates), 2)

    # Fallback: find any text below header
    below = [b["y"] for b in text_blocks if b["y"] > header_y + 5]
    if below:
        return round(min(below), 2)

    return round(header_y + 28, 2)


def _detect_transaction_font(page_data, header_y):
    """Detect the most common font in the table body (below header).

    Returns: font spec dict {font, size, color}.
    """
    text_blocks = page_data.get("text_blocks", [])

    # Collect font info from blocks below the header
    font_counts = Counter()
    font_colors = {}
    for b in text_blocks:
        if b["y"] > header_y + 10:
            key = (b["font"], round(b["size"], 1))
            font_counts[key] += 1
            font_colors[key] = b["color"]

    if not font_counts:
        return {"font": "ArialMT", "size": 8.0, "color": "#000000"}

    most_common = font_counts.most_common(1)[0][0]
    return {
        "font": most_common[0],
        "size": most_common[1],
        "color": font_colors[most_common],
    }


def _detect_spacing(page_data, header_y, transaction_font):
    """Detect row spacing by measuring Y gaps between consecutive text blocks in the table.

    Returns: (detail_line_spacing, summary_row_height, summary_to_detail_gap, detail_to_next_summary)
    """
    text_blocks = page_data.get("text_blocks", [])

    # Get all unique Y positions in the table body, sorted
    table_ys = sorted(set(
        round(b["y"], 1) for b in text_blocks
        if b["y"] > header_y + 10 and abs(b["size"] - transaction_font["size"]) < 1.5
    ))

    if len(table_ys) < 3:
        return 16.0, 32.5, 32.5, 37.8

    # Compute all consecutive gaps
    gaps = [round(table_ys[i + 1] - table_ys[i], 1) for i in range(len(table_ys) - 1)]

    if not gaps:
        return 16.0, 32.5, 32.5, 37.8

    # Cluster gaps into small (detail spacing) and large (summary spacing)
    gap_counter = Counter(gaps)
    sorted_gaps = sorted(gap_counter.keys())

    # The smallest common gap is detail_line_spacing
    detail_spacing = sorted_gaps[0] if sorted_gaps else 16.0

    # Larger gaps
    large_gaps = [g for g in sorted_gaps if g > detail_spacing * 1.5]

    if large_gaps:
        # summary_row_height is typically the most common large gap
        large_counter = {g: gap_counter[g] for g in large_gaps}
        summary_height = max(large_counter, key=large_counter.get)

        # summary_to_detail_gap is often same as summary_height or slightly different
        summary_to_detail = summary_height

        # detail_to_next_summary is often the largest gap
        detail_to_next = max(large_gaps) if max(large_gaps) != summary_height else summary_height + 5
    else:
        summary_height = detail_spacing * 2
        summary_to_detail = summary_height
        detail_to_next = summary_height + 5

    return (
        round(detail_spacing, 1),
        round(summary_height, 1),
        round(summary_to_detail, 1),
        round(detail_to_next, 1),
    )


def _detect_text_to_border_gap(page_data, header_y):
    """Detect the gap between rect top and text Y for table rows.

    Returns: text_to_border_gap (float).
    """
    rects = page_data.get("rects", [])
    text_blocks = page_data.get("text_blocks", [])

    # For each text block in the table, find the nearest rect above it
    gaps = []
    for b in text_blocks:
        if b["y"] <= header_y:
            continue
        for r in rects:
            # Rect top should be above the text, within 20pt
            if 0 < (b["y"] - r["y0"]) < 20 and (r["x1"] - r["x0"]) > 50:
                gaps.append(round(b["y"] - r["y0"], 2))

    if gaps:
        return round(_median(gaps), 2)

    return 11.45  # sensible default


def _detect_content_bottom(page_data, header_y, transaction_font):
    """Detect the maximum Y position of transaction text on a page.

    Best run on a full continuation page (page 2+).

    Returns: content_bottom (float).
    """
    text_blocks = page_data.get("text_blocks", [])

    table_ys = [
        b["y"] for b in text_blocks
        if b["y"] > header_y + 10 and abs(b["size"] - transaction_font["size"]) < 1.5
    ]

    if table_ys:
        return round(max(table_ys), 1)

    return 729.0


def _detect_browser_chrome(page_data):
    """Detect browser chrome (small text at page edges: URL, date, page number).

    Returns: dict with url_text, title_text, top_y, bottom_y, page_num_x.
    """
    text_blocks = page_data.get("text_blocks", [])
    page_height = page_data.get("height", 841.92)

    # Browser chrome typically uses the smallest font and appears at top/bottom edges
    if not text_blocks:
        return {"url_text": "about:blank", "title_text": "", "top_y": 15.9,
                "bottom_y": page_height - 23, "page_num_x": 551.2}

    # Find smallest font size
    min_size = min(b["size"] for b in text_blocks)

    # Top chrome: small text in the first 30pt of the page
    top_blocks = [b for b in text_blocks if b["y"] < 30 and abs(b["size"] - min_size) < 0.5]

    # Bottom chrome: small text in the last 30pt of the page
    bottom_blocks = [b for b in text_blocks if b["y"] > page_height - 30 and abs(b["size"] - min_size) < 0.5]

    top_y = round(top_blocks[0]["y"], 1) if top_blocks else 15.9
    bottom_y = round(bottom_blocks[0]["y"], 1) if bottom_blocks else page_height - 23

    # URL text is usually on the bottom-left
    url_text = "about:blank"
    for b in bottom_blocks:
        if b["x"] < 100:
            url_text = b["text"]
            break

    # Title text is usually on the top, center-ish
    title_text = ""
    for b in top_blocks:
        if b["x"] > 100:
            title_text = b["text"]
            break

    # Page number is on the bottom-right
    page_num_x = 551.2
    for b in bottom_blocks:
        if b["x"] > 400:
            page_num_x = round(b["x"], 1)
            break

    return {
        "url_text": url_text,
        "title_text": title_text,
        "top_y": top_y,
        "bottom_y": bottom_y,
        "page_num_x": page_num_x,
    }


def _detect_fonts(page_data, header_y, header_blocks, transaction_font):
    """Detect fonts for various roles from page 1 layout.

    Returns: dict of role → {font, size, color}.
    """
    text_blocks = page_data.get("text_blocks", [])

    fonts = {
        "transaction": transaction_font,
    }

    # Table header font from detected header blocks
    if header_blocks:
        b = header_blocks[0]
        fonts["table_header"] = {"font": b["font"], "size": round(b["size"], 2), "color": b["color"]}

    # Browser chrome font: smallest font on the page
    all_sizes = [(b["size"], b["font"], b["color"]) for b in text_blocks]
    if all_sizes:
        min_entry = min(all_sizes, key=lambda x: x[0])
        fonts["browser_chrome"] = {"font": min_entry[1], "size": round(min_entry[0], 2), "color": min_entry[2]}

    # Title font: largest font above the table
    above_table = [(b["size"], b["font"], b["color"]) for b in text_blocks if b["y"] < header_y and b["size"] > 10]
    if above_table:
        max_entry = max(above_table, key=lambda x: x[0])
        fonts["title"] = {"font": max_entry[1], "size": round(max_entry[0], 2), "color": max_entry[2]}

    # Header region fonts: classify by size and color
    header_region = [b for b in text_blocks if b["y"] < header_y and b["y"] > 30]

    # Group by (font, size) to find label vs value fonts
    font_groups = Counter()
    font_samples = {}
    for b in header_region:
        key = (b["font"], round(b["size"], 1), b["color"])
        font_groups[key] += 1
        font_samples[key] = b["text"]

    # The most common non-title font in header region is likely "label" or "value"
    for (f, s, c), count in font_groups.most_common():
        spec = {"font": f, "size": s, "color": c}
        if s > 10 and "title" not in fonts:
            fonts["title"] = spec
        elif c in ("#666666", "#999999", "#808080") and "label" not in fonts:
            fonts["label"] = spec
        elif "value" not in fonts and s < 10:
            fonts["value"] = spec

    # Fill defaults for missing roles
    default_font = transaction_font or {"font": "ArialMT", "size": 8.0, "color": "#000000"}
    for role in ["title", "account_type", "balance_large", "label", "value", "name",
                 "heading", "currency", "disclaimer", "link"]:
        if role not in fonts:
            fonts[role] = default_font

    return fonts


def _detect_header_fields(page_data, header_y):
    """Detect header fields (above the table on page 1).

    Returns a list of header field dicts. For the initial implementation,
    these store the raw text and position — template placeholders are resolved later.
    """
    text_blocks = page_data.get("text_blocks", [])

    fields = []
    for b in text_blocks:
        if b["y"] >= header_y:
            continue
        if b["y"] < 30:
            continue  # Skip browser chrome

        fields.append({
            "role": "__detected__",
            "x": round(b["x"], 1),
            "y": round(b["y"], 1),
            "font_key": "__auto__",
            "template": b["text"],
            "label": "",
            "original_font": {"font": b["font"], "size": round(b["size"], 2), "color": b["color"]},
        })

    return fields


def _detect_cont_page(page_data):
    """Detect continuation page parameters from page 2 data.

    Returns: (cont_table_top, cont_header_text_y, cont_first_content_y, cont_header_fields)
    """
    if not page_data:
        return 42.75, 52.8, 81.8, []

    text_blocks = page_data.get("text_blocks", [])
    rects = page_data.get("rects", [])

    # Find the table header on page 2
    header_blocks, header_y = _detect_table_header(page_data)

    if header_y is None:
        # Page 2 might not have a full header — look for any text
        ys = sorted(set(b["y"] for b in text_blocks if b["y"] > 30))
        if ys:
            header_y = ys[0]
        else:
            return 42.75, 52.8, 81.8, []

    # Continuation table top from rects
    cont_table_top = _detect_table_top(page_data, header_y)

    # Cont header text Y
    cont_header_text_y = header_y

    # First content Y: first text block below header with different Y
    content_ys = sorted(set(b["y"] for b in text_blocks if b["y"] > header_y + 5))
    cont_first_content_y = content_ys[0] if content_ys else header_y + 29

    # Continuation header fields: text blocks at the header Y
    cont_header_fields = []
    if header_blocks:
        for b in header_blocks:
            cont_header_fields.append({
                "text": b["text"].strip(),
                "x": round(b["x"], 1),
                "font_key": "table_header",
            })

    return (
        round(cont_table_top, 2),
        round(cont_header_text_y, 2),
        round(cont_first_content_y, 2),
        cont_header_fields,
    )


def _detect_grid_colors(page_data, header_y):
    """Detect grid border and separator colors from table rects.

    Returns: dict with "border" and "separator" color arrays.
    """
    rects = page_data.get("rects", [])

    # Collect colors from rects in the table area
    colors = []
    for r in rects:
        if r["y0"] > header_y - 20:
            fill = r.get("fill_color")
            stroke = r.get("stroke_color")
            if fill and fill != [1.0, 1.0, 1.0] and fill is not None:
                colors.append(("fill", tuple(fill) if isinstance(fill, list) else fill))
            if stroke and stroke != [1.0, 1.0, 1.0] and stroke is not None:
                colors.append(("stroke", tuple(stroke) if isinstance(stroke, list) else stroke))

    # Most common non-white color is the border color
    color_counter = Counter(c[1] for c in colors if isinstance(c[1], tuple))

    border_color = [0.8, 0.8, 0.8]  # default gray
    separator_color = [0.87, 0.89, 0.90]  # default light blue

    sorted_colors = color_counter.most_common()
    if sorted_colors:
        border_color = list(sorted_colors[0][0])
        if len(sorted_colors) > 1:
            separator_color = list(sorted_colors[1][0])

    return {"border": border_color, "separator": separator_color}


def _detect_detail_segments(page_data, header_y, col_bounds):
    """Detect detail row border segments (X ranges for detail top borders).

    Detail rows often merge some columns so their border segments differ from col_bounds.
    Detects from actual rects if possible, falls back to col_bounds.

    Returns: list of [x_start, x_end] pairs.
    """
    if not col_bounds or len(col_bounds) < 3:
        return []

    # For now, use a heuristic: first column is narrower, remaining merge
    # This matches HSBC pattern and is a reasonable default
    rects = page_data.get("rects", [])

    # Look for thin horizontal rects (height < 2pt) in the table body
    thin_rects = [r for r in rects
                  if r["y0"] > header_y + 20
                  and (r["y1"] - r["y0"]) < 2
                  and (r["x1"] - r["x0"]) > 20]

    if thin_rects:
        # Group by width pattern to find detail-specific segments
        segment_sets = Counter()
        for r in thin_rects:
            x0 = round(r["x0"], 0)
            x1 = round(r["x1"], 0)
            segment_sets[(x0, x1)] += 1

        # Get the 3 most common segments (detail rows typically have 3 segments)
        common = segment_sets.most_common(10)
        # Filter to segments that appear frequently
        if common:
            avg_count = sum(c for _, c in common) / len(common)
            frequent = [(s, c) for s, c in common if c >= avg_count * 0.3]
            if frequent:
                segments = sorted([list(s) for s, _ in frequent], key=lambda x: x[0])
                return segments

    # Fallback: derive from col_bounds
    return [[col_bounds[0] + 10, col_bounds[1]]] if len(col_bounds) >= 2 else []


# ── Main entry point ──────────────────────────────────────────────────────────

def detect_layout(layout, account_data=None):
    """Auto-detect all layout parameters from pdf_analyzer output.

    Args:
        layout: dict from analyze_pdf() with "pages" list
        account_data: optional dict of known account fields for header field matching

    Returns: BankProfile instance with all detected parameters.
    """
    pages = layout.get("pages", [])
    if not pages:
        raise ValueError("No pages in layout data")

    page1 = pages[0]
    page2 = pages[1] if len(pages) > 1 else None

    page_width = page1.get("width", 594.96)
    page_height = page1.get("height", 841.92)

    # ── Step 1: Detect table header on page 1 ──
    header_blocks, header_y = _detect_table_header(page1)
    if header_blocks is None:
        print("[LayoutDetector] WARNING: Could not detect table header. Using defaults.")
        from bank_profile import DEFAULT_HSBC_PROFILE
        return DEFAULT_HSBC_PROFILE

    print(f"[LayoutDetector] Table header at Y={header_y} with {len(header_blocks)} columns")

    # ── Step 2: Extract columns ──
    columns = _detect_columns(header_blocks)
    print(f"[LayoutDetector] Columns: {[c['name'] for c in columns]}")

    # ── Step 3: Detect column boundaries ──
    col_bounds = _detect_col_bounds(page1, header_y, page_width)
    if not col_bounds:
        # Infer from column positions
        all_x = sorted(set([c["x"] for c in columns] + [c["x1"] for c in columns]))
        col_bounds = [round(x, 1) for x in all_x]
    print(f"[LayoutDetector] Column bounds: {col_bounds}")

    # ── Step 4: Detect transaction font ──
    transaction_font = _detect_transaction_font(page1, header_y)
    print(f"[LayoutDetector] Transaction font: {transaction_font['font']} {transaction_font['size']}pt")

    # ── Step 5: Detect table boundaries ──
    p1_table_top = _detect_table_top(page1, header_y)
    p1_first_content_y = _detect_first_content_y(page1, header_y, transaction_font)
    print(f"[LayoutDetector] Page 1: table_top={p1_table_top}, first_content={p1_first_content_y}")

    # ── Step 6: Detect spacing ──
    # Use page 2 if available (more transaction rows for better measurement)
    spacing_page = page2 if page2 else page1
    spacing_header_y = header_y
    if page2:
        _, p2_header_y = _detect_table_header(page2)
        if p2_header_y:
            spacing_header_y = p2_header_y

    detail_spacing, summary_height, summary_to_detail, detail_to_next = \
        _detect_spacing(spacing_page, spacing_header_y, transaction_font)
    print(f"[LayoutDetector] Spacing: detail={detail_spacing}, summary={summary_height}, "
          f"s2d={summary_to_detail}, d2s={detail_to_next}")

    # ── Step 7: Detect text-to-border gap ──
    text_to_border_gap = _detect_text_to_border_gap(page1, header_y)
    print(f"[LayoutDetector] Text-to-border gap: {text_to_border_gap}")

    # ── Step 8: Detect content bottom ──
    if page2:
        content_bottom = _detect_content_bottom(page2, spacing_header_y, transaction_font)
    else:
        content_bottom = _detect_content_bottom(page1, header_y, transaction_font)
    print(f"[LayoutDetector] Content bottom: {content_bottom}")

    # ── Step 9: Detect browser chrome ──
    browser_chrome = _detect_browser_chrome(page1)
    footer_y = browser_chrome["bottom_y"]
    print(f"[LayoutDetector] Browser chrome: top_y={browser_chrome['top_y']}, bottom_y={footer_y}")

    # ── Step 10: Detect fonts ──
    fonts = _detect_fonts(page1, header_y, header_blocks, transaction_font)

    # ── Step 11: Detect header fields ──
    header_fields = _detect_header_fields(page1, header_y)
    print(f"[LayoutDetector] Detected {len(header_fields)} header fields")

    # ── Step 12: Detect continuation page layout ──
    cont_table_top, cont_header_text_y, cont_first_content_y, cont_header_fields = \
        _detect_cont_page(page2)
    print(f"[LayoutDetector] Continuation: table_top={cont_table_top}, "
          f"header_y={cont_header_text_y}, first_content={cont_first_content_y}")

    # ── Step 13: Detect grid colors ──
    grid_colors = _detect_grid_colors(page1, header_y)

    # ── Step 14: Detect detail border segments ──
    detail_border_segments = _detect_detail_segments(page1, header_y, col_bounds)

    # ── Step 15: Closing column segments ──
    # Similar to col_bounds but slightly adjusted (first starts after left border)
    closing_segments = col_bounds[:]
    if closing_segments and closing_segments[0] < 45:
        closing_segments[0] = closing_segments[0] + 0.5

    # ── Build profile ──
    profile = BankProfile(
        page_width=page_width,
        page_height=page_height,
        fonts=fonts,
        columns=columns,
        col_bounds=col_bounds,
        p1_table_header_y=header_y,
        p1_first_content_y=p1_first_content_y,
        p1_table_top=p1_table_top,
        p1_table_bottom=page_height - 42,
        cont_table_top=cont_table_top,
        cont_table_bottom=page_height - 42,
        cont_header_text_y=cont_header_text_y,
        cont_first_content_y=cont_first_content_y,
        summary_row_height=summary_height,
        detail_line_spacing=detail_spacing,
        summary_to_detail_gap=summary_to_detail,
        detail_to_next_summary=detail_to_next,
        content_bottom=content_bottom,
        footer_y=footer_y,
        grid_colors=grid_colors,
        text_to_border_gap=text_to_border_gap,
        header_fields=header_fields,
        cont_header_fields=cont_header_fields,
        browser_chrome=browser_chrome,
        has_footer=True,
        footer_gap=49.0,
        detail_border_segments=detail_border_segments,
        closing_col_segments=closing_segments,
    )

    return profile


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import json
    from pdf_analyzer import analyze_pdf

    if len(sys.argv) < 2:
        print("Usage: python layout_detector.py <statement.pdf> [--output profile.json]")
        sys.exit(1)

    pdf_path = sys.argv[1]
    output_path = "detected_profile.json"
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        output_path = sys.argv[idx + 1]

    print(f"Analyzing '{pdf_path}'...")
    layout = analyze_pdf(pdf_path, pages=[1, 2])

    print(f"\nDetecting layout...")
    profile = detect_layout(layout)

    profile_dict = profile.to_dict()
    with open(output_path, "w") as f:
        json.dump(profile_dict, f, indent=2)
    print(f"\nProfile saved → {output_path}")
    print(f"Columns detected: {[c['name'] for c in profile.columns]}")
    print(f"Page size: {profile.page_width} x {profile.page_height}")
