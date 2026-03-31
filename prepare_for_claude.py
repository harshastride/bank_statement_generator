"""
Prepare PDF data for Claude Chat — runs the analyzer and outputs
a clean JSON ready to paste into the Claude prompt.

Usage:
    python prepare_for_claude.py "YOUR_BANK_STATEMENT.pdf"

This will:
1. Run pdf_analyzer on pages 1 and 2
2. Extract images to extracted_images/
3. Save the analyzer JSON to claude_input.json
4. Print instructions on what to do next
"""

import json
import sys
import os

from pdf_analyzer import analyze_pdf


def prepare(pdf_path):
    if not os.path.exists(pdf_path):
        print(f"ERROR: File not found: {pdf_path}")
        sys.exit(1)

    print(f"Analyzing '{pdf_path}' (pages 1 and 2)...")
    print("=" * 60)

    image_dir = "extracted_images"
    layout = analyze_pdf(pdf_path, pages=[1, 2], image_dir=image_dir)

    # Strip image file paths (not needed for Claude) and simplify
    for page in layout["pages"]:
        # Keep images metadata but remove file paths
        for img in page.get("images", []):
            img.pop("file", None)
        for vr in page.get("vector_regions", []):
            vr.pop("file", None)

    output_file = "claude_input.json"
    with open(output_file, "w") as f:
        json.dump(layout, f, indent=2, default=str)

    # Count elements
    for page in layout["pages"]:
        p = page["page"]
        tb = len(page.get("text_blocks", []))
        r = len(page.get("rects", []))
        l = len(page.get("lines", []))
        print(f"  Page {p}: {tb} text blocks, {r} rects, {l} lines")

    file_size = os.path.getsize(output_file)
    print(f"\nSaved → {output_file} ({file_size:,} bytes)")

    print(f"""
{'=' * 60}
NEXT STEPS:
{'=' * 60}

1. Open Claude Chat → https://claude.ai

2. ATTACH the PDF file: {pdf_path}

3. Open the prompt guide:
   GUIDE_AI_PROFILE_EXTRACTION.md

4. Copy the ENTIRE prompt from the guide

5. In the prompt, REPLACE the placeholder:
   <<PASTE layout_for_claude.json CONTENTS HERE>>
   with the contents of: {output_file}

6. Send to Claude. It will return a JSON profile.

7. Save Claude's JSON response as: profile.json

8. Run:  python -c "
   import json
   from bank_profile import BankProfile
   with open('profile.json') as f:
       p = BankProfile.from_dict(json.load(f))
   print(f'Valid! {{len(p.columns)}} columns, {{len(p.header_fields)}} header fields')
   "
""")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python prepare_for_claude.py YOUR_BANK_STATEMENT.pdf")
        sys.exit(1)

    prepare(sys.argv[1])
