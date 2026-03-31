# How to Extract a BankProfile Using Claude Chat

## Step-by-Step Guide

---

## STEP 1: Run the PDF Analyzer on your bank statement

Open terminal and run:

```bash
cd /Users/kanalaharshareddy/Library/CloudStorage/OneDrive-Personal/Applications/BankStatementGenerator_V2

python pdf_analyzer.py "YOUR_BANK_STATEMENT.pdf" --pages 1,2 --output layout_for_claude.json --verbose
```

This gives you `layout_for_claude.json` with exact coordinates of every text block, rect, and line.

---

## STEP 2: Open Claude Chat

Go to https://claude.ai and start a new conversation.

---

## STEP 3: Upload the PDF

Click the attachment icon and upload your bank statement PDF.

---

## STEP 4: Paste the prompt below + the analyzer JSON

Copy the ENTIRE prompt below, then REPLACE the placeholder `<<PASTE layout_for_claude.json CONTENTS HERE>>` with the actual contents of `layout_for_claude.json`.

---

## THE PROMPT (copy everything between the lines)

---START PROMPT---

I have a bank statement PDF (attached). I also ran a PDF layout analyzer on it which extracted exact coordinates. I need you to produce a JSON config file that maps every visual element to its exact position so I can regenerate this PDF with different data using ReportLab.

## ANALYZER OUTPUT (exact coordinates from the PDF):

```json
<<PASTE layout_for_claude.json CONTENTS HERE>>
```

## WHAT I NEED YOU TO OUTPUT

Return a SINGLE JSON object with this EXACT structure. Use the EXACT coordinate values from the analyzer output above — do NOT estimate or round.

```json
{
  "page_width": <from analyzer: pages[0].width>,
  "page_height": <from analyzer: pages[0].height>,

  "fonts": {
    "browser_chrome": {"font": "<smallest font near page edges>", "size": <>, "color": "<hex>"},
    "title": {"font": "<largest font above table>", "size": <>, "color": "<hex>"},
    "account_type": {"font": "<font used for account type text>", "size": <>, "color": "<hex>"},
    "balance_large": {"font": "<font used for large balance display>", "size": <>, "color": "<hex>"},
    "label": {"font": "<font for field labels like 'Account number:'>", "size": <>, "color": "<hex>"},
    "value": {"font": "<font for field values>", "size": <>, "color": "<hex>"},
    "name": {"font": "<font for customer name>", "size": <>, "color": "<hex>"},
    "heading": {"font": "<font for section headings>", "size": <>, "color": "<hex>"},
    "table_header": {"font": "<font for column headers Date/Description/etc>", "size": <>, "color": "<hex>"},
    "transaction": {"font": "<most common font in table body>", "size": <>, "color": "<hex>"},
    "currency": {"font": "<font for currency labels>", "size": <>, "color": "<hex>"},
    "disclaimer": {"font": "<font for footer disclaimer text>", "size": <>, "color": "<hex>"},
    "link": {"font": "<font for hyperlinks>", "size": <>, "color": "<hex>"}
  },

  "columns": [
    {
      "name": "Date",
      "role": "date",
      "x": <X of date text in transaction rows (from analyzer text_blocks)>,
      "x1": <right edge of date column area>,
      "align": "left",
      "header_x": <X where "Date" header text starts>,
      "font": {"font": "<>", "size": <>, "color": "<>"}
    },
    {
      "name": "Description or Particulars or Narration",
      "role": "description",
      "x": <X of description text>,
      "x1": <right edge>,
      "align": "left",
      "header_x": <X of header text>,
      "font": {"font": "<>", "size": <>, "color": "<>"}
    },
    {
      "name": "Credit or Deposit",
      "role": "credit",
      "x": <RIGHT EDGE X where credit amounts are right-aligned to>,
      "x1": <same as x for right-aligned>,
      "align": "right",
      "header_x": <X where "Credit" header text starts>,
      "font": {"font": "<>", "size": <>, "color": "<>"}
    },
    {
      "name": "Debit or Withdrawal",
      "role": "debit",
      "x": <RIGHT EDGE X where debit amounts are right-aligned to>,
      "x1": <same>,
      "align": "right",
      "header_x": <X where "Debit" header text starts>,
      "font": {"font": "<>", "size": <>, "color": "<>"}
    },
    {
      "name": "Balance",
      "role": "balance",
      "x": <RIGHT EDGE X where balance amounts are right-aligned to>,
      "x1": <same>,
      "align": "right",
      "header_x": <X where "Balance" header text starts>,
      "font": {"font": "<>", "size": <>, "color": "<>"}
    }
  ],

  "col_bounds": [<leftmost rect edge X>, <col1 right edge>, <col2 right edge>, ..., <rightmost rect edge X>],

  "p1_table_header_y": <Y of the column header text "Date", "Description", etc on page 1>,
  "p1_first_content_y": <Y of the FIRST transaction text below the header on page 1>,
  "p1_table_top": <Y of topmost table border rect on page 1>,
  "p1_table_bottom": <Y of bottommost table border rect on page 1>,

  "cont_table_top": <Y of topmost table rect on page 2>,
  "cont_table_bottom": <Y of bottommost table rect on page 2>,
  "cont_header_text_y": <Y of column header text on page 2>,
  "cont_first_content_y": <Y of first transaction text on page 2>,

  "summary_row_height": <Y gap between two consecutive transaction DATE lines>,
  "detail_line_spacing": <Y gap between description lines WITHIN the same transaction>,
  "summary_to_detail_gap": <Y gap from a date/amount line DOWN to its first description line>,
  "detail_to_next_summary": <Y gap from last description line UP to next transaction's date line>,

  "content_bottom": <maximum Y of any transaction text on a full page (page 2)>,
  "footer_y": <Y of the browser chrome footer text at page bottom>,

  "grid_colors": {
    "border": [<r 0-1>, <g 0-1>, <b 0-1>],
    "separator": [<r 0-1>, <g 0-1>, <b 0-1>]
  },
  "text_to_border_gap": <distance between a text Y and the rect border ABOVE it>,

  "header_fields": [
    <for EACH text block above the table on page 1, create one entry:>
    {
      "role": "<see rules below>",
      "x": <exact X from analyzer>,
      "y": <exact Y from analyzer>,
      "font_key": "<which fonts key to use>",
      "template": "<text with {placeholders} or literal>",
      "label": "<human label for editable fields, empty for static>"
    }
  ],

  "cont_header_fields": [
    {"text": "<column header text on page 2, e.g. Balance>", "x": <X>, "font_key": "table_header"}
  ],

  "browser_chrome": {
    "url_text": "<URL text at page bottom, e.g. about:blank>",
    "title_text": "<title text in browser chrome header>",
    "top_y": <Y of top browser chrome text>,
    "bottom_y": <Y of bottom browser chrome text>,
    "page_num_x": <X of page number like '1/5'>
  },

  "has_footer": true,
  "footer_gap": <Y gap between last transaction and footer/disclaimer text>,

  "detail_border_segments": [[<x0>, <x1>], [<x0>, <x1>], ...],
  "closing_col_segments": [<x0>, <x1>, <x2>, ...],

  "header_row_rects_pattern": [<see GRID RECT PATTERN RULES below>],
  "summary_row_rects_pattern": [<see GRID RECT PATTERN RULES below>],
  "detail_row_rects_pattern": [<see GRID RECT PATTERN RULES below>]
}
```

## RULES FOR header_fields

CRITICAL: You MUST use EXACTLY these placeholder names. No variations:
`{customer_name}`, `{address_line_1}`, `{address_line_2}`, `{city_state}`, `{pin}`,
`{account_number}`, `{account_type}`, `{branch}`, `{micr}`, `{ifsc}`, `{nominee}`,
`{current_balance}`, `{overdraft}`, `{currency}`,
`{download_date}`, `{print_date}`, `{print_time}`

DO NOT use variations like {micr_code}, {ifsc_code}, {nominee_registered}, {overdraft_limit}, {address_line_3}, {address_line_4}.

The first 2 entries MUST be browser chrome:
```json
{"role": "__chrome__", "x": 24.0, "y": <top_y>, "font_key": "browser_chrome", "template": "{print_date}, {print_time}", "label": ""},
{"role": "__chrome__", "x": 280.6, "y": <top_y>, "font_key": "browser_chrome", "template": "Account summary and transactions", "label": ""}
```

DO NOT include date range fields (Date range:, start date, end date, dash) — these are handled by the code automatically.

For the remaining text blocks above the transaction table on page 1:
- Bank name/title → `"role": "__static__", "template": "EXACT BANK NAME TEXT"`
- Account type → `"role": "account_type", "template": "{account_type}"`
- Balance display → `"role": "current_balance_right", "template": "{current_balance}"` (x = right edge)
- Currency label → `"role": "currency_label", "template": "{currency}"`
- Customer name → `"role": "customer_name", "template": "{customer_name}"`
- Address lines → `"role": "address_line_1"` / `"address_line_2"` / `"city_state"` / `"pin"`
- Account number label → `"role": "__static__", "template": "Account number:"`
- Account number value → `"role": "account_number", "template": "{account_number}"`
- Branch → `"role": "branch", "template": "Branch Name:{branch}"`
- MICR → `"role": "micr", "template": "MICR Code:{micr}"`
- IFSC → `"role": "ifsc", "template": "IFSC Code:{ifsc}"`
- Nominee → `"role": "nominee", "template": "Nominee Registered:{nominee}"`
- Mixed label+value → `"role": "__computed__", "template": "Available balance:{current_balance} {currency}"`
- "Search results" heading → `"role": "__static__", "template": "Search results"`

## RULES FOR COLUMNS

- For LEFT-ALIGNED columns (Date, Description): `"x"` = the X position where text starts (left edge)
- For RIGHT-ALIGNED columns (Credit, Debit, Balance): `"x"` = the X position of the RIGHT EDGE of the rightmost amount text in that column. Look at the `x1` values of amount text_blocks in the analyzer data.
- `"header_x"` = always the X where the column header text starts (left edge of "Date", "Credit", etc.)

## RULES FOR SPACING

Look at the transaction text_blocks in the analyzer data. Find 2-3 consecutive transactions.

IMPORTANT: `summary_row_height` is NOT the full height of a transaction group. It is the distance used to advance from one summary line to the next when there are NO detail lines between them. Typically 28-35pt, NOT 100+pt.

- `summary_row_height` = Y difference between two ADJACENT transaction date lines (when they have no description lines between them). If all transactions have descriptions, use: summary_to_detail_gap + detail_line_spacing + detail_to_next_summary - detail_line_spacing. Typically ~32pt.
- `detail_line_spacing` = Y difference between two consecutive description lines WITHIN the same transaction. Typically ~16pt.
- `summary_to_detail_gap` = Y of first description line MINUS Y of the date/amount line above it. Typically ~32pt.
- `detail_to_next_summary` = Y of next transaction's date line MINUS Y of previous transaction's last description line. Typically ~35-40pt.
- `text_to_border_gap` = take any transaction text Y, find the nearest rect border ABOVE it, compute the difference. Typically ~11pt.

## RULES FOR col_bounds

These are the X coordinates of the vertical grid lines in the table. Extract them from the `rects` in the analyzer output — look at rects that are in the table area and collect their unique x0 and x1 values. Sort them left to right.

## RULES FOR detail_border_segments

Detail rows (description lines) often have DIFFERENT horizontal borders than summary rows. Look at thin rects (height < 2pt) in the table body area. Group them by their X ranges to find the segments used for detail rows.

## RULES FOR closing_col_segments

The very last horizontal line at the bottom of the table. Collect the X coordinates of the segments that make up this closing line.

## GRID RECT PATTERN RULES

This is the most important part. Look at the rects in the analyzer output that are inside the transaction table area. Each transaction row has a repeating pattern of rects (borders, backgrounds, separators). You need to express these as templates.

There are 3 row types:
1. **header** — the table header row ("Date", "Description", "Credit", etc.)
2. **summary** — a transaction row (date + amounts on one line)
3. **detail** — a description/narration line below a transaction

For each row type, look at the rects on ONE row and express each rect relative to that row's top border:

```json
{
  "x0": <absolute X left>,
  "x1": <absolute X right>,
  "y_offset": <Y offset from the row's border_y (= text_y - text_to_border_gap). 0 = at border_y>,
  "height": <rect height in points>,
  "fill_color": [<r>, <g>, <b>],
  "stroke_color": [<r>, <g>, <b>],
  "width": 0.75,
  "use_row_height": false,
  "at_row_bottom": false
}
```

Special flags:
- `"use_row_height": true` — the rect stretches to fill the row's full height (for vertical borders and cell backgrounds). Set `height` to 0 when using this.
- `"at_row_bottom": true` — the rect is positioned at the bottom of the row (e.g., bottom border). Use `"y_offset_from_bottom": 0` instead of `"y_offset"`.

How to identify the patterns:
1. Find the table header row rects — they typically have: top border segments, left vertical border, white cell backgrounds, bottom border segments
2. Find a summary/transaction row — typically has: separator line (often lighter color), left vertical border, white backgrounds
3. Find a detail row — typically has: fewer/merged border segments, left vertical border, merged white backgrounds (fewer cells than summary)

Look at the analyzer rects data. Filter to rects that are in the table Y range. Group by Y position to see which rects belong to the same row. Then express each group as a pattern.

The X positions in the patterns are ABSOLUTE (not relative) — they define the exact column boundaries of the grid.

## CHECKLIST — VERIFY ALL OF THESE BEFORE RETURNING

1. Column header fonts (`columns[].font`) must match the `table_header` font role (usually BOLD like Arial-BoldMT), NOT the regular transaction font
2. `cont_header_fields` — look at page 2 of the PDF. Only include the column headers that ACTUALLY appear on page 2. Many banks only show "Balance" or a subset on continuation pages, NOT all 5 columns
3. `summary_row_height` must be ~28-35pt (the Y spacing between two consecutive date lines). It is NOT the full height of a transaction group (which would be 100-200pt). If unsure, use 32.5
4. Use ONLY these placeholder names — no variations, no invented names:
   `{customer_name}`, `{address_line_1}`, `{address_line_2}`, `{city_state}`, `{pin}`, `{account_number}`, `{account_type}`, `{branch}`, `{micr}`, `{ifsc}`, `{nominee}`, `{current_balance}`, `{overdraft}`, `{currency}`, `{download_date}`, `{print_date}`, `{print_time}`
5. Do NOT include date range fields (Date range:, start date, dash, end date) in header_fields — the code handles date range display automatically
6. The first 2 entries in header_fields MUST be `__chrome__` entries for browser print header
7. No right-side vertical border rects in any row pattern. The original PDF has left border only, no right border
8. Left vertical border rects must have `"y_offset": 0` (not 0.53) so the border is one continuous line with no gaps between rows

IMPORTANT: Return ONLY the JSON. No explanation. No markdown code fences. Just the raw JSON object.

---END PROMPT---

---

## STEP 5: Claude returns the JSON

Claude will analyze the PDF image + the exact coordinates and return a complete JSON profile.

Save Claude's response as `profile.json`.

---

## STEP 6: Validate and use the profile

```bash
# Validate the profile loads correctly
python -c "
import json
from bank_profile import BankProfile

with open('profile.json') as f:
    data = json.load(f)

profile = BankProfile.from_dict(data)
print(f'Columns: {[c[\"name\"] for c in profile.columns]}')
print(f'Page: {profile.page_width} x {profile.page_height}')
print(f'Table header Y: {profile.p1_table_header_y}')
print(f'First content Y: {profile.p1_first_content_y}')
print(f'Header fields: {len(profile.header_fields)}')
print(f'Fonts: {list(profile.fonts.keys())}')
print('Profile is VALID!')
"
```

---

## STEP 7: Build the template (one command)

```bash
python build_template.py "YOUR_BANK_STATEMENT.pdf" profile.json
```

This single command:
- Runs `pdf_analyzer.py` to extract images and layout from the PDF
- Extracts footer/disclaimer content from the last page
- Combines everything with your profile.json into `template.json`
- Ready to generate PDFs!

---

## STEP 8: Register the bank (optional)

```bash
# Add the bank to the registry
python -c "
import json, shutil, os

BANK_ID = 'your_bank_id'   # e.g., 'hdfc', 'sbi', 'icici'
BANK_NAME = 'Your Bank'     # e.g., 'HDFC Bank'

banks_dir = 'banks'
bank_dir = f'{banks_dir}/{BANK_ID}'
os.makedirs(bank_dir, exist_ok=True)

# Copy template and images
shutil.copy2('template.json', f'{bank_dir}/template.json')
if os.path.exists('extracted_images'):
    shutil.copytree('extracted_images', f'{bank_dir}/template_images', dirs_exist_ok=True)

# Update banks.json
with open(f'{banks_dir}/banks.json') as f:
    banks = json.load(f)

banks = [b for b in banks if b['id'] != BANK_ID]
banks.append({
    'id': BANK_ID,
    'name': BANK_NAME,
    'full_name': BANK_NAME,
    'logo': BANK_ID,
    'sample_account': {
        'customer_name': '',
        'account_number': '',
        'account_type': '',
        'current_balance': '0.00',
        'currency': 'INR',
    },
})

with open(f'{banks_dir}/banks.json', 'w') as f:
    json.dump(banks, f, indent=2)

print(f'Bank {BANK_NAME} registered as {BANK_ID}')
"
```

---

## STEP 9: Test PDF generation

```bash
python pdf_template_builder.py generate \
  -t template.json \
  -d account_data.json \
  -c transactions.csv \
  -o test_output.pdf
```

Open `test_output.pdf` and verify the layout matches the original!

---

## TIPS

- If Claude's first output isn't perfect, tell it what's wrong (e.g., "the Credit column is 10pt too far right") and it will adjust
- You can iterate 2-3 times with Claude to get pixel-perfect results
- This is MUCH faster than manual iteration in code — what took weeks for HSBC can take 10-15 minutes per bank
- Save the working profile.json — you never need to redo it for the same bank
