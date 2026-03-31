"""
PDF Rebuilder — Recreate a PDF from layout.json (produced by pdf_analyzer.py).

Usage:
    python pdf_rebuilder.py layout.json [--output rebuilt.pdf]

The rebuilt PDF uses ReportLab canvas for exact coordinate placement.
"""

import argparse
import json
import os
import platform
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor, Color
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ── TTF Font Registration ─────────────────────────────────────────────────

_FONTS_REGISTERED = False


def _find_font_dirs():
    """Return a list of system font directories to search."""
    system = platform.system()
    if system == "Darwin":
        return [
            "/System/Library/Fonts/Supplemental",
            "/System/Library/Fonts",
            "/Library/Fonts",
            os.path.expanduser("~/Library/Fonts"),
        ]
    elif system == "Windows":
        return [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")]
    else:  # Linux
        return ["/usr/share/fonts/truetype", "/usr/share/fonts", "/usr/local/share/fonts",
                os.path.expanduser("~/.fonts")]


def _register_ttf_fonts():
    """Register real Arial (and other) TTF fonts with ReportLab."""
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    _FONTS_REGISTERED = True

    # Map of ReportLab font name → possible TTF filenames
    font_files = {
        "Arial":            ["Arial.ttf", "arial.ttf"],
        "Arial-Bold":       ["Arial Bold.ttf", "arialbd.ttf", "Arial-Bold.ttf"],
        "Arial-Italic":     ["Arial Italic.ttf", "ariali.ttf", "Arial-Italic.ttf"],
        "Arial-BoldItalic": ["Arial Bold Italic.ttf", "arialbi.ttf", "Arial-BoldItalic.ttf"],
    }

    font_dirs = _find_font_dirs()

    for font_name, filenames in font_files.items():
        for font_dir in font_dirs:
            for filename in filenames:
                path = os.path.join(font_dir, filename)
                if os.path.exists(path):
                    try:
                        pdfmetrics.registerFont(TTFont(font_name, path))
                    except Exception:
                        pass
                    break
            else:
                continue
            break


# ── Font mapping ────────────────────────────────────────────────────────────

FONT_MAP = {
    # Arial family → real Arial TTF
    "arialmt": "Arial",
    "arial": "Arial",
    "arial-boldmt": "Arial-Bold",
    "arial-bold": "Arial-Bold",
    "arial-italicmt": "Arial-Italic",
    "arial-bolditalicmt": "Arial-BoldItalic",
    # Times family
    "timesnewromanpsmt": "Times-Roman",
    "timesnewromanps-boldmt": "Times-Bold",
    "timesnewromanps-italicmt": "Times-Italic",
    "timesnewromanps-bolditalicmt": "Times-BoldItalic",
    # Courier family
    "couriernewpsmt": "Courier",
    "couriernewps-boldmt": "Courier-Bold",
    # Calibri → Arial
    "calibri": "Arial",
    "calibri-bold": "Arial-Bold",
    # Verdana → Arial
    "verdana": "Arial",
    "verdana-bold": "Arial-Bold",
}


def map_font(pdf_font_name):
    """Map a PDF font name to a registered TTF or built-in font."""
    if not pdf_font_name:
        return "Arial"

    # Direct lookup (case-insensitive, stripped)
    key = pdf_font_name.lower().replace(" ", "")
    # Remove common prefixes like AAAAAA+
    if "+" in key:
        key = key.split("+", 1)[1]

    if key in FONT_MAP:
        return FONT_MAP[key]

    # Heuristic fallback
    if "bold" in key and "italic" in key:
        return "Arial-BoldItalic"
    if "bold" in key:
        return "Arial-Bold"
    if "italic" in key or "oblique" in key:
        return "Arial-Italic"
    if "courier" in key or "mono" in key:
        return "Courier"
    if "times" in key or "serif" in key:
        return "Times-Roman"

    return "Arial"


# ── Color conversion ────────────────────────────────────────────────────────

def parse_color(color_value, default=(0, 0, 0)):
    """Convert various color formats to a reportlab Color."""
    if color_value is None:
        return Color(*default)

    if isinstance(color_value, str):
        if color_value.startswith("#"):
            return HexColor(color_value)
        return Color(*default)

    if isinstance(color_value, (list, tuple)):
        if len(color_value) == 1:
            # Grayscale
            g = color_value[0]
            return Color(g, g, g)
        if len(color_value) == 3:
            return Color(*color_value)
        if len(color_value) == 4:
            # CMYK → approximate RGB
            c, m, y, k = color_value
            r = (1 - c) * (1 - k)
            g = (1 - m) * (1 - k)
            b = (1 - y) * (1 - k)
            return Color(r, g, b)

    return Color(*default)


# ── Helpers ─────────────────────────────────────────────────────────────────

def _draw_image_placeholder(c, x, rl_y, img):
    """Draw a gray placeholder box where an image should be."""
    c.setStrokeColor(Color(0.85, 0.85, 0.85))
    c.setFillColor(Color(0.95, 0.95, 0.95))
    c.rect(x, rl_y, img["width"], img["height"], stroke=1, fill=1)
    c.setFillColor(Color(0.6, 0.6, 0.6))
    c.setFont("Arial", 6)
    label = img.get("file") or img.get("name") or "?"
    c.drawString(x + 2, rl_y + img["height"] / 2, f"[missing: {os.path.basename(label)}]")


# ── Rebuild ─────────────────────────────────────────────────────────────────

def rebuild_pdf(layout, output_path):
    """Recreate a PDF from the analyzed layout."""

    # Register real TTF fonts before creating any canvas
    _register_ttf_fonts()

    first_page = layout["pages"][0]
    page_w = first_page["width"]
    page_h = first_page["height"]

    c = canvas.Canvas(output_path, pagesize=(page_w, page_h))

    # Set initial font to Arial so ReportLab doesn't default to Helvetica
    c.setFont("Arial", 10)

    # Match source PDF metadata (Chrome print-to-PDF)
    c.setAuthor("")
    c.setCreator("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36")
    c.setProducer("Skia/PDF m146")
    c.setTitle("Account summary and transactions")
    c.setSubject("")

    for page_data in layout["pages"]:
        ph = page_data["height"]

        # Draw rectangles (backgrounds first)
        for rect in page_data.get("rects", []):
            x0 = rect["x0"]
            y0_top = rect["y0"]
            w = rect["x1"] - rect["x0"]
            h = rect["y1"] - rect["y0"]
            rl_y = ph - y0_top - h  # bottom-left corner in ReportLab coords

            fill_color = rect.get("fill_color")
            stroke_color = rect.get("stroke_color")

            if fill_color:
                c.setFillColor(parse_color(fill_color))
            else:
                c.setFillColor(Color(1, 1, 1, 0))  # transparent

            if stroke_color:
                c.setStrokeColor(parse_color(stroke_color))
                c.setLineWidth(rect.get("width", 0.75))
                c.rect(x0, rl_y, w, h, stroke=1,
                       fill=1 if fill_color else 0)
            elif fill_color:
                c.rect(x0, rl_y, w, h, stroke=0, fill=1)

        # Draw lines
        for line in page_data.get("lines", []):
            c.setStrokeColor(parse_color(line.get("color"), default=(0.8, 0.8, 0.8)))
            c.setLineWidth(line.get("width", 0.75))
            c.line(line["x0"], ph - line["y0"],
                   line["x1"], ph - line["y1"])

        # Draw text
        for block in page_data.get("text_blocks", []):
            font = map_font(block.get("font"))
            size = block.get("size", 10)
            x = block["x"]
            rl_y = ph - block["y"] - size  # baseline approximation

            c.setFont(font, size)
            # Apply font color
            text_color = block.get("color", "#000000")
            if text_color and text_color.startswith("#"):
                c.setFillColor(HexColor(text_color))
            else:
                c.setFillColor(Color(0, 0, 0))
            c.drawString(x, rl_y, block["text"])

            # Add clickable hyperlink if present
            link_url = block.get("link")
            if link_url:
                text_width = c.stringWidth(block["text"], font, size)
                # Draw underline
                c.setStrokeColor(HexColor(text_color) if text_color and text_color.startswith("#") else Color(0, 0, 0))
                c.setLineWidth(0.5)
                c.line(x, rl_y - 1, x + text_width, rl_y - 1)
                # Create clickable link rect
                c.linkURL(link_url, (x, rl_y - 2, x + text_width, rl_y + size), relative=0)

        # Draw raster images
        for img in page_data.get("images", []):
            x = img["x"]
            rl_y = ph - img["y"] - img["height"]
            img_file = img.get("file")

            if img_file and os.path.exists(img_file):
                try:
                    c.drawImage(
                        img_file, x, rl_y,
                        width=img["width"], height=img["height"],
                        preserveAspectRatio=False,
                        mask="auto",
                    )
                except Exception as e:
                    print(f"  Warning: could not embed '{img_file}': {e}")
                    _draw_image_placeholder(c, x, rl_y, img)
            else:
                _draw_image_placeholder(c, x, rl_y, img)

        # Draw vector regions (logos, icons rendered as PNG snapshots)
        for vr in page_data.get("vector_regions", []):
            x = vr["x"]
            rl_y = ph - vr["y"] - vr["height"]
            vr_file = vr.get("file")

            if vr_file and os.path.exists(vr_file):
                try:
                    c.drawImage(
                        vr_file, x, rl_y,
                        width=vr["width"], height=vr["height"],
                        preserveAspectRatio=False,
                        mask="auto",
                    )
                except Exception as e:
                    print(f"  Warning: could not embed vector region '{vr_file}': {e}")
                    _draw_image_placeholder(c, x, rl_y, vr)
            else:
                _draw_image_placeholder(c, x, rl_y, vr)

        c.showPage()

    c.save()

    # Post-process: remove unused Helvetica font and clean ReportLab traces
    _clean_pdf_metadata(output_path)

    print(f"Rebuilt PDF → {output_path}")


def _clean_pdf_metadata(pdf_path):
    """Remove unused fonts and any remaining ReportLab traces from the PDF."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)

        # Override metadata to remove any ReportLab leftovers
        doc.set_metadata({
            "title": "Account summary and transactions",
            "author": "",
            "subject": "",
            "keywords": "",
            "creator": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
            "producer": "Skia/PDF m146",
        })

        # Replace ReportLab's initial Helvetica (F1) reference with Arial (F2)
        # in each page's content stream, then remove the unused Helvetica font
        # Find the Arial font refname (F2) from page 0
        arial_refname = None
        helv_refname = None
        for item in doc[0].get_fonts():
            _, _, _, fname, refname, _ = item
            if "Arial" in fname and "Bold" not in fname:
                arial_refname = refname
            if fname == "Helvetica":
                helv_refname = refname

        if arial_refname and helv_refname:
            font_dict_xrefs_cleaned = set()
            for page in doc:
                # Replace /F1 with /F2 in content streams
                for xref in page.get_contents():
                    stream = doc.xref_stream(xref)
                    stream = stream.replace(
                        f"/{helv_refname} ".encode(),
                        f"/{arial_refname} ".encode()
                    )
                    doc.update_stream(xref, stream)

                # Remove Helvetica entry from the page's font resource dictionary
                res = doc.xref_get_key(page.xref, "Resources/Font")
                if res[0] == "xref":
                    font_dict_xref = int(res[1].split()[0])
                    if font_dict_xref not in font_dict_xrefs_cleaned:
                        font_dict_xrefs_cleaned.add(font_dict_xref)
                        doc.xref_set_key(font_dict_xref, helv_refname, "null")

        # Re-save with garbage collection to strip orphaned objects
        tmp_path = pdf_path + ".tmp"
        doc.save(tmp_path, garbage=4, deflate=True)
        doc.close()
        os.replace(tmp_path, pdf_path)
    except ImportError:
        pass  # fitz not available, skip cleanup
    except Exception:
        pass  # non-critical, skip


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild PDF from layout JSON")
    parser.add_argument("layout", help="Path to layout.json (from pdf_analyzer.py)")
    parser.add_argument("--output", "-o", default="rebuilt.pdf",
                        help="Output PDF path (default: rebuilt.pdf)")
    args = parser.parse_args()

    with open(args.layout) as f:
        layout = json.load(f)

    print(f"Rebuilding {len(layout['pages'])} pages...")
    rebuild_pdf(layout, args.output)
