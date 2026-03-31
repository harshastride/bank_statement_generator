"""
PDF Analyzer — Extract layout (text positions, fonts, lines, rects, images) from any PDF.
Outputs a structured JSON file for inspection or use by pdf_rebuilder.py.
Images are extracted to an 'extracted_images/' folder alongside the layout JSON.

Usage:
    python pdf_analyzer.py input.pdf [--output layout.json] [--pages 1,2,3]
"""

import argparse
import json
import os
import pdfplumber
import fitz  # PyMuPDF — for extracting actual image data


def extract_images_from_pdf(pdf_path, output_dir, pages=None):
    """Extract all embedded images from a PDF using PyMuPDF.

    Returns a dict mapping (page_num, image_index) → saved file path.
    Images are deduplicated by their xref (internal PDF object ID).
    """
    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    image_map = {}  # (page_num, img_idx) → file_path
    seen_xrefs = {}  # xref → file_path (dedup)

    for page_idx in range(len(doc)):
        page_num = page_idx + 1
        if pages and page_num not in pages:
            continue

        page = doc[page_idx]
        img_list = page.get_images(full=True)

        for img_idx, img_info in enumerate(img_list):
            xref = img_info[0]

            # Dedup: reuse already-extracted image
            if xref in seen_xrefs:
                image_map[(page_num, img_idx)] = seen_xrefs[xref]
                continue

            # Extract image bytes
            base_image = doc.extract_image(xref)
            if not base_image:
                continue

            img_bytes = base_image["image"]
            img_ext = base_image.get("ext", "png")
            filename = f"page{page_num}_img{img_idx}.{img_ext}"
            filepath = os.path.join(output_dir, filename)

            with open(filepath, "wb") as f:
                f.write(img_bytes)

            image_map[(page_num, img_idx)] = filepath
            seen_xrefs[xref] = filepath

    doc.close()
    print(f"  Extracted {len(seen_xrefs)} unique raster images → {output_dir}/")
    return image_map


def extract_vector_regions_as_images(pdf_path, output_dir, pages=None, dpi=300):
    """Render vector drawing regions (logos, icons) as high-res PNG snapshots.

    Groups nearby vector drawings into regions and renders each region
    as a cropped PNG at the specified DPI.

    Returns a list of dicts per page: [{page, x, y, width, height, file}, ...]
    """
    os.makedirs(output_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    all_regions = {}  # page_num → [region, ...]

    for page_idx in range(len(doc)):
        page_num = page_idx + 1
        if pages and page_num not in pages:
            continue

        page = doc[page_idx]
        drawings = page.get_drawings()
        if not drawings:
            continue

        # Find non-white filled vector drawings (likely logos/icons)
        vector_rects = []
        for d in drawings:
            fill = d.get("fill")
            if fill and fill != (1.0, 1.0, 1.0):
                vector_rects.append(d["rect"])

        if not vector_rects:
            continue

        # Group nearby vector drawings into regions (cluster by proximity)
        regions = _cluster_rects(vector_rects, gap=5.0)

        page_regions = []
        for idx, region_rect in enumerate(regions):
            # Add small padding
            clip = fitz.Rect(
                region_rect.x0 - 1,
                region_rect.y0 - 1,
                region_rect.x1 + 1,
                region_rect.y1 + 1,
            )
            # Render just this region at high DPI
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat, clip=clip, alpha=True)

            filename = f"page{page_num}_vector{idx}.png"
            filepath = os.path.join(output_dir, filename)
            pix.save(filepath)

            page_regions.append({
                "x": round(clip.x0, 2),
                "y": round(clip.y0, 2),
                "width": round(clip.width, 2),
                "height": round(clip.height, 2),
                "file": filepath,
                "type": "vector_region",
            })

        if page_regions:
            all_regions[page_num] = page_regions

    doc.close()
    total = sum(len(v) for v in all_regions.values())
    print(f"  Extracted {total} vector regions as PNG → {output_dir}/")
    return all_regions


def _cluster_rects(rects, gap=5.0):
    """Cluster nearby rectangles into merged regions."""
    if not rects:
        return []

    # Start each rect as its own cluster
    clusters = [fitz.Rect(r) for r in rects]
    merged = True

    while merged:
        merged = False
        new_clusters = []
        used = set()

        for i in range(len(clusters)):
            if i in used:
                continue
            current = fitz.Rect(clusters[i])
            # Expand slightly for proximity test
            expanded = fitz.Rect(
                current.x0 - gap, current.y0 - gap,
                current.x1 + gap, current.y1 + gap,
            )

            for j in range(i + 1, len(clusters)):
                if j in used:
                    continue
                if expanded.intersects(clusters[j]):
                    current = current | clusters[j]  # union
                    expanded = fitz.Rect(
                        current.x0 - gap, current.y0 - gap,
                        current.x1 + gap, current.y1 + gap,
                    )
                    used.add(j)
                    merged = True

            new_clusters.append(current)
            used.add(i)

        clusters = new_clusters

    return clusters


def match_pdfplumber_images_to_extracted(page_images, extracted_map, page_num):
    """Match pdfplumber's image position data with PyMuPDF's extracted files."""
    matched = []
    for idx, img in enumerate(page_images):
        file_path = extracted_map.get((page_num, idx))
        matched.append({
            "x": round(img["x0"], 2),
            "y": round(img["top"], 2),
            "width": round(img["x1"] - img["x0"], 2),
            "height": round(img["bottom"] - img["top"], 2),
            "name": img.get("name", ""),
            "file": file_path,
        })
    return matched


def _extract_span_colors(fitz_page):
    """Extract per-span color + position data from PyMuPDF.

    Returns a list of (x, y, text, hex_color) for matching against pdfplumber words.
    """
    spans = []
    data = fitz_page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:  # text blocks only
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                color_int = span["color"]
                r = (color_int >> 16) & 0xFF
                g = (color_int >> 8) & 0xFF
                b = color_int & 0xFF
                hex_color = f"#{r:02X}{g:02X}{b:02X}"
                spans.append({
                    "x": round(span["origin"][0], 2),
                    "y": round(span["bbox"][1], 2),  # top of bbox
                    "x1": round(span["bbox"][2], 2),
                    "text": span["text"],
                    "color": hex_color,
                })
    return spans


def _match_color_to_word(word_x, word_y, word_x1, color_spans, tolerance=2.0):
    """Find the best matching span color for a pdfplumber word by position overlap."""
    best = None
    best_overlap = 0
    for span in color_spans:
        # Check vertical proximity
        if abs(span["y"] - word_y) > tolerance:
            continue
        # Check horizontal overlap
        overlap_start = max(word_x, span["x"])
        overlap_end = min(word_x1, span["x1"])
        overlap = max(0, overlap_end - overlap_start)
        if overlap > best_overlap:
            best_overlap = overlap
            best = span["color"]
    return best or "#000000"


def extract_page_layout(page, page_num, image_map=None, vector_regions=None, fitz_page=None):
    """Extract all layout elements from a single page."""

    # Extract span-level colors from PyMuPDF
    color_spans = _extract_span_colors(fitz_page) if fitz_page else []

    # Extract words with font metadata
    words = page.extract_words(
        x_tolerance=3,
        y_tolerance=3,
        keep_blank_chars=True,
        extra_attrs=["fontname", "size"],
    )
    text_blocks = []
    for w in words:
        x = round(w["x0"], 2)
        y = round(w["top"], 2)
        x1 = round(w["x1"], 2)
        color = _match_color_to_word(x, y, x1, color_spans) if color_spans else "#000000"
        text_blocks.append({
            "text": w["text"],
            "x": x,
            "y": y,
            "x1": x1,
            "y1": round(w["bottom"], 2),
            "font": w.get("fontname", "Unknown"),
            "size": round(w.get("size", 10), 2),
            "color": color,
        })

    # Extract lines
    lines = []
    for l in page.lines:
        lines.append({
            "x0": round(l["x0"], 2),
            "y0": round(l["top"], 2),
            "x1": round(l["x1"], 2),
            "y1": round(l["bottom"], 2),
            "width": round(l.get("linewidth", 0.75), 2),
            "color": l.get("stroking_color"),
        })

    # Extract rectangles
    rects = []
    for r in page.rects:
        rects.append({
            "x0": round(r["x0"], 2),
            "y0": round(r["top"], 2),
            "x1": round(r["x1"], 2),
            "y1": round(r["bottom"], 2),
            "stroke_color": r.get("stroking_color"),
            "fill_color": r.get("non_stroking_color"),
            "width": round(r.get("linewidth", 0.75), 2),
        })

    # Extract images (with file paths if available)
    if image_map:
        images = match_pdfplumber_images_to_extracted(page.images, image_map, page_num)
    else:
        images = []
        for img in page.images:
            images.append({
                "x": round(img["x0"], 2),
                "y": round(img["top"], 2),
                "width": round(img["x1"] - img["x0"], 2),
                "height": round(img["bottom"] - img["top"], 2),
                "name": img.get("name", ""),
                "file": None,
            })

    # Include vector regions (logos, icons rendered as PNG)
    vr = vector_regions.get(page_num, []) if vector_regions else []

    return {
        "page": page_num,
        "width": round(page.width, 2),
        "height": round(page.height, 2),
        "text_blocks": text_blocks,
        "lines": lines,
        "rects": rects,
        "images": images,
        "vector_regions": vr,
    }


def analyze_pdf(pdf_path, pages=None, image_dir="extracted_images"):
    """Analyze a PDF and return structured layout data."""
    result = {"source": pdf_path, "pages": [], "image_dir": image_dir}

    # Step 1: Extract actual image data using PyMuPDF
    print(f"  Extracting images from '{pdf_path}'...")
    image_map = extract_images_from_pdf(pdf_path, image_dir, pages)

    # Step 1b: Extract vector regions (logos, icons) as PNG snapshots
    print(f"  Extracting vector regions...")
    vector_regions = extract_vector_regions_as_images(pdf_path, image_dir, pages)

    # Step 2: Extract layout using pdfplumber + PyMuPDF (for colors)
    fitz_doc = fitz.open(pdf_path)
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        result["total_pages"] = total

        for i, page in enumerate(pdf.pages):
            page_num = i + 1
            if pages and page_num not in pages:
                continue

            fitz_page = fitz_doc[i]
            layout = extract_page_layout(page, page_num, image_map, vector_regions, fitz_page)
            result["pages"].append(layout)

            # Print summary
            print(f"Page {page_num}/{total}: "
                  f"{len(layout['text_blocks'])} text blocks, "
                  f"{len(layout['lines'])} lines, "
                  f"{len(layout['rects'])} rects, "
                  f"{len(layout['images'])} images, "
                  f"{len(layout['vector_regions'])} vector regions")

    fitz_doc.close()
    return result


def print_detailed(layout):
    """Print human-readable layout details to stdout."""
    for page in layout["pages"]:
        print(f"\n{'='*60}")
        print(f"PAGE {page['page']}  ({page['width']} x {page['height']} pt)")
        print(f"{'='*60}")

        if page["text_blocks"]:
            print(f"\n  TEXT BLOCKS ({len(page['text_blocks'])}):")
            for b in page["text_blocks"]:
                color = b.get('color', '#000000')
                print(f"    x={b['x']:>7.1f}  y={b['y']:>7.1f}  "
                      f"size={b['size']:>5.2f}  {color}  "
                      f"font={b['font']:<25s}  '{b['text']}'")

        if page["lines"]:
            print(f"\n  LINES ({len(page['lines'])}):")
            for l in page["lines"]:
                print(f"    ({l['x0']:.1f}, {l['y0']:.1f}) → "
                      f"({l['x1']:.1f}, {l['y1']:.1f})  "
                      f"width={l['width']}")

        if page["rects"]:
            print(f"\n  RECTANGLES ({len(page['rects'])}):")
            for r in page["rects"]:
                w = r["x1"] - r["x0"]
                h = r["y1"] - r["y0"]
                print(f"    ({r['x0']:.1f}, {r['y0']:.1f})  "
                      f"{w:.1f} x {h:.1f}")

        if page["images"]:
            print(f"\n  IMAGES ({len(page['images'])}):")
            for img in page["images"]:
                print(f"    ({img['x']:.1f}, {img['y']:.1f})  "
                      f"{img['width']:.1f} x {img['height']:.1f}  "
                      f"file={img.get('file', 'N/A')}")

        if page.get("vector_regions"):
            print(f"\n  VECTOR REGIONS ({len(page['vector_regions'])}):")
            for vr in page["vector_regions"]:
                print(f"    ({vr['x']:.1f}, {vr['y']:.1f})  "
                      f"{vr['width']:.1f} x {vr['height']:.1f}  "
                      f"file={vr.get('file', 'N/A')}")


def collect_font_summary(layout):
    """Summarize all fonts and sizes used in the document."""
    fonts = {}
    for page in layout["pages"]:
        for b in page["text_blocks"]:
            key = (b["font"], b["size"])
            if key not in fonts:
                fonts[key] = {"count": 0, "sample": b["text"][:50]}
            fonts[key]["count"] += 1

    print(f"\n{'='*60}")
    print("FONT SUMMARY")
    print(f"{'='*60}")
    for (font, size), info in sorted(fonts.items(), key=lambda x: (-x[0][1], x[0][0])):
        print(f"  {font:<30s}  {size:>6.2f}pt  ({info['count']:>4d} uses)  "
              f"e.g. '{info['sample']}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract layout from any PDF")
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument("--output", "-o", default="layout.json",
                        help="Output JSON file (default: layout.json)")
    parser.add_argument("--pages", "-p", default=None,
                        help="Comma-separated page numbers to analyze (default: all)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print detailed layout to stdout")
    args = parser.parse_args()

    pages = None
    if args.pages:
        pages = [int(p.strip()) for p in args.pages.split(",")]

    layout = analyze_pdf(args.pdf, pages)

    # Save JSON
    with open(args.output, "w") as f:
        json.dump(layout, f, indent=2, default=str)
    print(f"\nSaved layout → {args.output}")

    # Always show font summary
    collect_font_summary(layout)

    if args.verbose:
        print_detailed(layout)
