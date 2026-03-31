"""
Build Template — Combines Claude's profile.json with analyzer data into a
complete template.json ready for PDF generation.

This is the ONLY script you run after getting profile.json from Claude.
It handles everything: analyzer, images, footer, and final template assembly.

Usage:
    python build_template.py "YOUR_BANK_STATEMENT.pdf" profile.json

    # Optionally specify output paths:
    python build_template.py "statement.pdf" profile.json --output template.json --image-dir template_images
"""

import argparse
import json
import os
import sys

from pdf_analyzer import analyze_pdf
from bank_profile import BankProfile
from pdf_template_builder import _extract_last_page_footer


def build_template(pdf_path, profile_path, output_path="template.json", image_dir="template_images"):
    """Combine profile.json + PDF analysis into a complete template.json."""

    if not os.path.exists(pdf_path):
        print(f"ERROR: PDF not found: {pdf_path}")
        sys.exit(1)
    if not os.path.exists(profile_path):
        print(f"ERROR: Profile not found: {profile_path}")
        sys.exit(1)

    # ── Step 1: Load and validate profile ──
    print(f"Loading profile from '{profile_path}'...")
    with open(profile_path) as f:
        profile_dict = json.load(f)

    profile = BankProfile.from_dict(profile_dict)
    print(f"  Columns: {[c['name'] for c in profile.columns]}")
    print(f"  Page: {profile.page_width} x {profile.page_height}")
    print(f"  Fonts: {len(profile.fonts)} roles")
    print(f"  Header fields: {len(profile.header_fields)}")
    print(f"  Rect patterns: header={len(profile.header_row_rects_pattern)}, "
          f"summary={len(profile.summary_row_rects_pattern)}, "
          f"detail={len(profile.detail_row_rects_pattern)}")

    # ── Step 2: Run PDF analyzer (extracts images + layout) ──
    print(f"\nAnalyzing PDF '{pdf_path}'...")
    layout = analyze_pdf(pdf_path, pages=[1, 2], image_dir=image_dir)

    # ── Step 3: Extract last page footer ──
    print("\nExtracting footer from last page...")
    footer_data = _extract_last_page_footer(pdf_path, profile)
    if footer_data:
        print(f"  Footer: {len(footer_data['spans'])} text spans, "
              f"gap={footer_data['gap_from_last_txn']}pt, "
              f"height={footer_data['total_height']}pt")
    else:
        print("  No footer found (this is fine for some banks)")

    # ── Step 4: Assemble template.json ──
    print("\nAssembling template...")
    template = {
        "source_pdf": os.path.abspath(pdf_path),
        "profile": profile_dict,
        "page_width": layout["pages"][0]["width"],
        "page_height": layout["pages"][0]["height"],
        "image_dir": os.path.abspath(image_dir),
        "page1": layout["pages"][0],
        "page2": layout["pages"][1] if len(layout["pages"]) > 1 else None,
        "last_page_footer": footer_data,
    }

    with open(output_path, "w") as f:
        json.dump(template, f, indent=2, default=str)

    size_kb = os.path.getsize(output_path) / 1024
    print(f"\nDone! Template saved -> {output_path} ({size_kb:.1f} KB)")
    print(f"Images saved -> {image_dir}/")
    print(f"""
{'=' * 60}
TEMPLATE IS READY! You can now generate PDFs:
{'=' * 60}

  python pdf_template_builder.py generate \\
    -t {output_path} \\
    -d account_data.json \\
    -c transactions.csv \\
    -o output.pdf

Or use the web frontend (python app.py) to create jobs with this bank.
""")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build a complete template.json from a PDF + Claude's profile.json"
    )
    parser.add_argument("pdf", help="Path to the bank statement PDF")
    parser.add_argument("profile", help="Path to profile.json (from Claude)")
    parser.add_argument("--output", "-o", default="template.json",
                        help="Output template path (default: template.json)")
    parser.add_argument("--image-dir", default="template_images",
                        help="Directory for extracted images (default: template_images)")

    args = parser.parse_args()
    build_template(args.pdf, args.profile, args.output, args.image_dir)
