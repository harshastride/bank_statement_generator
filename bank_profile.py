"""
BankProfile — Data model holding all layout parameters for a bank statement PDF.

Replaces the 50+ hardcoded constants in pdf_template_builder.py with a structured
config that can be auto-detected from any bank's source PDF and stored in template.json.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional


# ── Column name aliases ───────────────────────────────────────────────────────
# Maps semantic roles to possible column header names found in bank PDFs.

COLUMN_ALIASES = {
    "date": {"date", "txn date", "transaction date", "value date", "val date", "posting date"},
    "description": {"description", "particulars", "narration", "details", "transaction details",
                    "remark", "remarks"},
    "credit": {"credit", "deposit", "cr", "credits", "deposits", "credit amount", "cr amt"},
    "debit": {"debit", "withdrawal", "dr", "debits", "withdrawals", "debit amount", "dr amt"},
    "balance": {"balance", "closing balance", "running balance", "bal", "available balance"},
    "amount": {"amount", "amt", "transaction amount"},
    "cheque": {"cheque", "chq", "chq no", "cheque no", "ref", "ref no", "reference"},
}


def _normalize_column_name(name):
    """Map a detected column header to a canonical role name."""
    lower = name.strip().lower()
    for role, aliases in COLUMN_ALIASES.items():
        if lower in aliases:
            return role
    return lower  # return as-is if no match


@dataclass
class ColumnDef:
    """Definition of a single table column."""
    name: str           # Original header text (e.g., "Credit")
    role: str           # Canonical role (e.g., "credit")
    x: float            # X position for left-aligned text, or right-edge for right-aligned
    x1: float           # Right edge of the column area
    align: str = "left"  # "left" or "right"
    header_x: float = 0.0  # X where the header text is placed
    font: dict = field(default_factory=dict)  # Font spec for header text

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


@dataclass
class HeaderField:
    """A field in the page 1 header region (above the table)."""
    role: str           # "customer_name", "account_number", or "__static__" for labels
    x: float
    y: float
    font_key: str       # Key into BankProfile.fonts (e.g., "label", "value", "title")
    template: str       # Text with {placeholders} or literal text
    label: str = ""     # Human-readable label for the frontend form

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


@dataclass
class BankProfile:
    """Complete layout profile for a bank statement PDF."""

    # Page dimensions
    page_width: float = 594.96
    page_height: float = 841.92

    # Fonts by role
    fonts: dict = field(default_factory=dict)
    # Expected keys: "title", "account_type", "balance_large", "label", "value",
    # "name", "heading", "table_header", "transaction", "currency",
    # "disclaimer", "link", "browser_chrome"

    # Column definitions (variable-length)
    columns: list = field(default_factory=list)
    col_bounds: list = field(default_factory=list)  # Grid vertical X boundaries

    # Table positions — Page 1
    p1_table_header_y: float = 399.2
    p1_first_content_y: float = 427.6
    p1_table_top: float = 389.1
    p1_table_bottom: float = 799.83

    # Table positions — Continuation pages
    cont_table_top: float = 42.75
    cont_table_bottom: float = 799.83
    cont_header_text_y: float = 52.8
    cont_first_content_y: float = 81.8

    # Spacing
    summary_row_height: float = 32.5
    detail_line_spacing: float = 16.0
    summary_to_detail_gap: float = 32.5
    detail_to_next_summary: float = 37.8

    # Boundaries
    content_bottom: float = 729.0
    footer_y: float = 819.1

    # Grid styling
    grid_colors: dict = field(default_factory=dict)
    # Expected keys: "border" (e.g. [0.8,0.8,0.8]), "separator" (e.g. [0.87,0.89,0.90])
    text_to_border_gap: float = 11.45

    # Header fields (page 1, above table)
    header_fields: list = field(default_factory=list)

    # Continuation page header fields
    cont_header_fields: list = field(default_factory=list)

    # Browser chrome (print header/footer)
    browser_chrome: dict = field(default_factory=dict)
    # Expected keys: "url_text", "title_text", "top_y", "bottom_y"

    # Footer/disclaimer
    has_footer: bool = True
    footer_gap: float = 49.0

    # Detail row grid segments (X ranges for detail row top borders)
    # These differ from col_bounds because detail rows merge some columns
    detail_border_segments: list = field(default_factory=list)

    # Closing line column segments
    closing_col_segments: list = field(default_factory=list)

    # Grid rect patterns per row type — each is a list of rect templates
    # with positions relative to border_y (= text_y - text_to_border_gap).
    # If "use_row_height" is true, the rect height = the row's dynamic height.
    # These are produced by Claude analyzing the source PDF rects.
    header_row_rects_pattern: list = field(default_factory=list)
    summary_row_rects_pattern: list = field(default_factory=list)
    detail_row_rects_pattern: list = field(default_factory=list)

    def get_column(self, role_or_name):
        """Find a column by canonical role or original name (case-insensitive).

        Supports aliases: get_column("description") matches "Particulars", etc.
        """
        target_role = _normalize_column_name(role_or_name)
        for col in self.columns:
            if col["role"] == target_role:
                return col
            if col["name"].strip().lower() == role_or_name.strip().lower():
                return col
        return None

    def get_column_x(self, role_or_name, default=0.0):
        """Get the X position for a column by role/name."""
        col = self.get_column(role_or_name)
        return col["x"] if col else default

    def get_font(self, role, default=None):
        """Get font spec by role name."""
        return self.fonts.get(role, default or {"font": "ArialMT", "size": 8.0, "color": "#000000"})

    def to_dict(self):
        """Serialize to a JSON-compatible dict."""
        return {
            "page_width": self.page_width,
            "page_height": self.page_height,
            "fonts": self.fonts,
            "columns": self.columns,
            "col_bounds": self.col_bounds,
            "p1_table_header_y": self.p1_table_header_y,
            "p1_first_content_y": self.p1_first_content_y,
            "p1_table_top": self.p1_table_top,
            "p1_table_bottom": self.p1_table_bottom,
            "cont_table_top": self.cont_table_top,
            "cont_table_bottom": self.cont_table_bottom,
            "cont_header_text_y": self.cont_header_text_y,
            "cont_first_content_y": self.cont_first_content_y,
            "summary_row_height": self.summary_row_height,
            "detail_line_spacing": self.detail_line_spacing,
            "summary_to_detail_gap": self.summary_to_detail_gap,
            "detail_to_next_summary": self.detail_to_next_summary,
            "content_bottom": self.content_bottom,
            "footer_y": self.footer_y,
            "grid_colors": self.grid_colors,
            "text_to_border_gap": self.text_to_border_gap,
            "header_fields": self.header_fields,
            "cont_header_fields": self.cont_header_fields,
            "browser_chrome": self.browser_chrome,
            "has_footer": self.has_footer,
            "footer_gap": self.footer_gap,
            "detail_border_segments": self.detail_border_segments,
            "closing_col_segments": self.closing_col_segments,
            "header_row_rects_pattern": self.header_row_rects_pattern,
            "summary_row_rects_pattern": self.summary_row_rects_pattern,
            "detail_row_rects_pattern": self.detail_row_rects_pattern,
        }

    @classmethod
    def from_dict(cls, d):
        """Deserialize from a dict (e.g., from template.json["profile"]).

        Handles None values explicitly — if a key is present but null,
        the default is used instead.
        """
        def g(key, default):
            """Get with None-safe fallback."""
            val = d.get(key)
            return val if val is not None else default

        return cls(
            page_width=g("page_width", 594.96),
            page_height=g("page_height", 841.92),
            fonts=g("fonts", {}),
            columns=g("columns", []),
            col_bounds=g("col_bounds", []),
            p1_table_header_y=g("p1_table_header_y", 399.2),
            p1_first_content_y=g("p1_first_content_y", 427.6),
            p1_table_top=g("p1_table_top", 389.1),
            p1_table_bottom=g("p1_table_bottom", 799.83),
            cont_table_top=g("cont_table_top", 42.75),
            cont_table_bottom=g("cont_table_bottom", 799.83),
            cont_header_text_y=g("cont_header_text_y", 52.8),
            cont_first_content_y=g("cont_first_content_y", 81.8),
            summary_row_height=g("summary_row_height", 32.5),
            detail_line_spacing=g("detail_line_spacing", 16.0),
            summary_to_detail_gap=g("summary_to_detail_gap", 32.5),
            detail_to_next_summary=g("detail_to_next_summary", 37.8),
            content_bottom=g("content_bottom", 729.0),
            footer_y=g("footer_y", 819.1),
            grid_colors=g("grid_colors", {}),
            text_to_border_gap=g("text_to_border_gap", 11.45),
            header_fields=g("header_fields", []),
            cont_header_fields=g("cont_header_fields", []),
            browser_chrome=g("browser_chrome", {}),
            has_footer=g("has_footer", True),
            footer_gap=g("footer_gap", 49.0),
            detail_border_segments=g("detail_border_segments", []),
            closing_col_segments=g("closing_col_segments", []),
            header_row_rects_pattern=g("header_row_rects_pattern", []),
            summary_row_rects_pattern=g("summary_row_rects_pattern", []),
            detail_row_rects_pattern=g("detail_row_rects_pattern", []),
        )


# ── Default HSBC Profile ─────────────────────────────────────────────────────
# Populated from the current hardcoded constants in pdf_template_builder.py.
# Used as fallback when template.json has no "profile" key (backward compat).

DEFAULT_HSBC_PROFILE = BankProfile(
    page_width=594.96,
    page_height=841.92,

    fonts={
        "browser_chrome": {"font": "ArialMT", "size": 7.99, "color": "#000000"},
        "title": {"font": "ArialMT", "size": 11.70, "color": "#D40D0D"},
        "account_type": {"font": "ArialMT", "size": 11.70, "color": "#333333"},
        "balance_large": {"font": "ArialMT", "size": 11.70, "color": "#333333"},
        "label": {"font": "ArialMT", "size": 7.45, "color": "#666666"},
        "value": {"font": "ArialMT", "size": 7.45, "color": "#333333"},
        "name": {"font": "ArialMT", "size": 7.45, "color": "#212529"},
        "heading": {"font": "ArialMT", "size": 10.64, "color": "#212529"},
        "table_header": {"font": "Arial-BoldMT", "size": 7.45, "color": "#333333"},
        "transaction": {"font": "ArialMT", "size": 8.51, "color": "#333333"},
        "currency": {"font": "ArialMT", "size": 7.45, "color": "#666666"},
        "disclaimer": {"font": "ArialMT", "size": 8.51, "color": "#212529"},
        "link": {"font": "ArialMT", "size": 8.51, "color": "#0000EE"},
    },

    columns=[
        {"name": "Date", "role": "date", "x": 53.9, "x1": 130.0, "align": "left",
         "header_x": 53.9, "font": {"font": "Arial-BoldMT", "size": 7.45, "color": "#333333"}},
        {"name": "Description", "role": "description", "x": 138.3, "x1": 330.0, "align": "left",
         "header_x": 138.3, "font": {"font": "Arial-BoldMT", "size": 7.45, "color": "#333333"}},
        {"name": "Credit", "role": "credit", "x": 337.3, "x1": 337.3, "align": "right",
         "header_x": 315.8, "font": {"font": "Arial-BoldMT", "size": 7.45, "color": "#333333"}},
        {"name": "Debit", "role": "debit", "x": 437.2, "x1": 437.2, "align": "right",
         "header_x": 418.5, "font": {"font": "Arial-BoldMT", "size": 7.45, "color": "#333333"}},
        {"name": "Balance", "role": "balance", "x": 537.0, "x1": 537.0, "align": "right",
         "header_x": 508.4, "font": {"font": "Arial-BoldMT", "size": 7.45, "color": "#333333"}},
    ],

    col_bounds=[42.8, 133.2, 242.8, 342.8, 442.3, 542.3, 553.5],

    p1_table_header_y=399.2,
    p1_first_content_y=427.6,
    p1_table_top=389.1,
    p1_table_bottom=799.83,

    cont_table_top=42.75,
    cont_table_bottom=799.83,
    cont_header_text_y=52.8,
    cont_first_content_y=81.8,

    summary_row_height=32.5,
    detail_line_spacing=16.0,
    summary_to_detail_gap=32.5,
    detail_to_next_summary=37.8,

    content_bottom=729.0,
    footer_y=819.1,

    grid_colors={
        "border": [0.8, 0.8, 0.8],
        "separator": [0.8706, 0.8863, 0.902],
    },
    text_to_border_gap=11.45,

    header_fields=[
        {"role": "__chrome__", "x": 24.0, "y": 15.9, "font_key": "browser_chrome",
         "template": "{print_date}, {print_time}", "label": ""},
        {"role": "__chrome__", "x": 280.6, "y": 15.9, "font_key": "browser_chrome",
         "template": "Account summary and transactions", "label": ""},
        {"role": "__static__", "x": 42.8, "y": 109.6, "font_key": "title",
         "template": "HSBC Account Statement", "label": ""},
        {"role": "account_type", "x": 42.8, "y": 125.6, "font_key": "account_type",
         "template": "{account_type}", "label": "Account Type"},
        {"role": "current_balance_right", "x": 538.0, "y": 125.6, "font_key": "balance_large",
         "template": "{current_balance}", "label": ""},
        {"role": "__static__", "x": 540.7, "y": 128.9, "font_key": "currency",
         "template": "{currency}", "label": ""},
        {"role": "customer_name", "x": 42.8, "y": 148.1, "font_key": "name",
         "template": "{customer_name}", "label": "Customer Name"},
        {"role": "__computed__", "x": 442.5, "y": 148.6, "font_key": "label",
         "template": "Available balance:{current_balance} {currency}", "label": ""},
        {"role": "address_line_1", "x": 42.8, "y": 166.2, "font_key": "label",
         "template": "{address_line_1}", "label": "Address Line 1"},
        {"role": "__computed__", "x": 473.0, "y": 166.2, "font_key": "label",
         "template": "Overdraft limit:{overdraft} {currency}", "label": ""},
        {"role": "address_line_2", "x": 42.8, "y": 183.7, "font_key": "label",
         "template": "{address_line_2}", "label": "Address Line 2"},
        {"role": "__computed__", "x": 418.7, "y": 183.7, "font_key": "label",
         "template": "Date of statement download:{download_date}", "label": ""},
        {"role": "city_state", "x": 42.8, "y": 201.3, "font_key": "label",
         "template": "{city_state}", "label": "City/State"},
        {"role": "pin", "x": 42.8, "y": 218.8, "font_key": "label",
         "template": "{pin}", "label": "PIN"},
        {"role": "__static__", "x": 42.8, "y": 236.4, "font_key": "label",
         "template": "Account number:", "label": ""},
        {"role": "account_number", "x": 104.4, "y": 236.4, "font_key": "value",
         "template": "{account_number}", "label": "Account Number"},
        {"role": "branch", "x": 42.8, "y": 253.9, "font_key": "value",
         "template": "Branch Name:{branch}", "label": "Branch"},
        {"role": "micr", "x": 42.8, "y": 271.5, "font_key": "label",
         "template": "MICR Code:{micr}", "label": "MICR Code"},
        {"role": "ifsc", "x": 42.8, "y": 289.1, "font_key": "value",
         "template": "IFSC Code:{ifsc}", "label": "IFSC Code"},
        {"role": "nominee", "x": 42.8, "y": 306.6, "font_key": "label",
         "template": "Nominee Registered:{nominee}", "label": "Nominee"},
        {"role": "__static__", "x": 42.8, "y": 348.3, "font_key": "heading",
         "template": "Search results", "label": ""},
    ],

    cont_header_fields=[
        {"text": "Balance", "x": 508.4, "font_key": "table_header"},
    ],

    browser_chrome={
        "url_text": "about:blank",
        "title_text": "Account summary and transactions",
        "top_y": 15.9,
        "bottom_y": 819.1,
        "page_num_x": 551.2,
    },

    has_footer=True,
    footer_gap=49.0,

    detail_border_segments=[
        [52.3, 133.2],
        [133.2, 342.8],
        [342.8, 546.6],
    ],

    closing_col_segments=[43.3, 133.2, 242.8, 342.8, 442.3, 542.3, 553.0],

    # HSBC header row rect pattern (y_offset relative to border_y)
    # Pattern: top border segments + left vertical + white cell backgrounds + bottom border segments
    header_row_rects_pattern=[
        # Top border (6 column segments, 0.53pt tall)
        {"x0": 42.8, "x1": 133.2, "y_offset": 0, "height": 0.53, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75},
        {"x0": 133.2, "x1": 242.8, "y_offset": 0, "height": 0.53, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75},
        {"x0": 242.8, "x1": 342.8, "y_offset": 0, "height": 0.53, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75},
        {"x0": 342.8, "x1": 442.3, "y_offset": 0, "height": 0.53, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75},
        {"x0": 442.3, "x1": 542.3, "y_offset": 0, "height": 0.53, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75},
        {"x0": 542.3, "x1": 553.5, "y_offset": 0, "height": 0.53, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75},
        # Left vertical border
        {"x0": 42.8, "x1": 43.3, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75},
        # White cell backgrounds
        {"x0": 43.3, "x1": 133.2, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [1,1,1], "stroke_color": [1,1,1], "width": 0.75},
        {"x0": 133.7, "x1": 242.8, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [1,1,1], "stroke_color": [1,1,1], "width": 0.75},
        {"x0": 243.3, "x1": 342.8, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [1,1,1], "stroke_color": [1,1,1], "width": 0.75},
        {"x0": 343.3, "x1": 442.3, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [1,1,1], "stroke_color": [1,1,1], "width": 0.75},
        {"x0": 442.8, "x1": 542.3, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [1,1,1], "stroke_color": [1,1,1], "width": 0.75},
        {"x0": 542.8, "x1": 553.5, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [1,1,1], "stroke_color": [1,1,1], "width": 0.75},
        # Bottom border (6 segments, placed at row_height offset)
        {"x0": 42.8, "x1": 133.2, "y_offset_from_bottom": 0, "height": 0.53, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75, "at_row_bottom": True},
        {"x0": 133.2, "x1": 242.8, "y_offset_from_bottom": 0, "height": 0.53, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75, "at_row_bottom": True},
        {"x0": 242.8, "x1": 342.8, "y_offset_from_bottom": 0, "height": 0.53, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75, "at_row_bottom": True},
        {"x0": 342.8, "x1": 442.3, "y_offset_from_bottom": 0, "height": 0.53, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75, "at_row_bottom": True},
        {"x0": 442.3, "x1": 542.3, "y_offset_from_bottom": 0, "height": 0.53, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75, "at_row_bottom": True},
        {"x0": 542.3, "x1": 553.5, "y_offset_from_bottom": 0, "height": 0.53, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75, "at_row_bottom": True},
    ],

    # HSBC summary row rect pattern
    # Pattern: light blue separator + left vertical + white backgrounds
    summary_row_rects_pattern=[
        # Separator line (light blue, 6 segments)
        {"x0": 42.8, "x1": 133.2, "y_offset": 0, "height": 0.53, "fill_color": [0.8706,0.8863,0.902], "stroke_color": [0.8706,0.8863,0.902], "width": 0.75},
        {"x0": 133.2, "x1": 242.8, "y_offset": 0, "height": 0.53, "fill_color": [0.8706,0.8863,0.902], "stroke_color": [0.8706,0.8863,0.902], "width": 0.75},
        {"x0": 242.8, "x1": 342.8, "y_offset": 0, "height": 0.53, "fill_color": [0.8706,0.8863,0.902], "stroke_color": [0.8706,0.8863,0.902], "width": 0.75},
        {"x0": 342.8, "x1": 442.3, "y_offset": 0, "height": 0.53, "fill_color": [0.8706,0.8863,0.902], "stroke_color": [0.8706,0.8863,0.902], "width": 0.75},
        {"x0": 442.3, "x1": 542.3, "y_offset": 0, "height": 0.53, "fill_color": [0.8706,0.8863,0.902], "stroke_color": [0.8706,0.8863,0.902], "width": 0.75},
        {"x0": 542.3, "x1": 553.5, "y_offset": 0, "height": 0.53, "fill_color": [0.8706,0.8863,0.902], "stroke_color": [0.8706,0.8863,0.902], "width": 0.75},
        # Left vertical border
        {"x0": 42.8, "x1": 43.3, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75},
        # White cell backgrounds
        {"x0": 43.3, "x1": 133.2, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [1,1,1], "stroke_color": [1,1,1], "width": 0.75},
        {"x0": 133.7, "x1": 242.8, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [1,1,1], "stroke_color": [1,1,1], "width": 0.75},
        {"x0": 243.3, "x1": 342.8, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [1,1,1], "stroke_color": [1,1,1], "width": 0.75},
        {"x0": 343.3, "x1": 442.3, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [1,1,1], "stroke_color": [1,1,1], "width": 0.75},
        {"x0": 442.8, "x1": 542.3, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [1,1,1], "stroke_color": [1,1,1], "width": 0.75},
        {"x0": 542.8, "x1": 553.5, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [1,1,1], "stroke_color": [1,1,1], "width": 0.75},
    ],

    # HSBC detail row rect pattern
    # Pattern: 3 top border segments + left vertical + 3 merged white backgrounds
    detail_row_rects_pattern=[
        # Top border (3 segments — detail rows merge columns)
        {"x0": 52.3, "x1": 133.2, "y_offset": 0, "height": 0.53, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75},
        {"x0": 133.2, "x1": 342.8, "y_offset": 0, "height": 0.53, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75},
        {"x0": 342.8, "x1": 546.6, "y_offset": 0, "height": 0.53, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75},
        # Left vertical border
        {"x0": 42.8, "x1": 43.3, "y_offset": 0, "use_row_height": True, "height": 0, "fill_color": [0.8,0.8,0.8], "stroke_color": [0.8,0.8,0.8], "width": 0.75},
        # White backgrounds (3 merged areas)
        {"x0": 43.3, "x1": 133.2, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [1,1,1], "stroke_color": [1,1,1], "width": 0.75},
        {"x0": 133.2, "x1": 342.8, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [1,1,1], "stroke_color": [1,1,1], "width": 0.75},
        {"x0": 342.8, "x1": 553.0, "y_offset": 0.53, "use_row_height": True, "height": 0, "fill_color": [1,1,1], "stroke_color": [1,1,1], "width": 0.75},
    ],
)
