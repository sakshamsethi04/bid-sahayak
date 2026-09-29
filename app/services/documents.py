"""Document processing layer: text extraction (PDF text layer or Tesseract OCR),
word boxes for evidence highlighting, and page rendering."""
import io
import re
import time
from pathlib import Path

import pdfplumber
from PIL import Image, ImageDraw

from ..config import OCR_ENABLED

try:
    import pytesseract
    from pdf2image import convert_from_path
    pytesseract.get_tesseract_version()
    TESSERACT_OK = True
except Exception:  # tesseract binary missing
    TESSERACT_OK = False

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def is_image(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXT


def _ocr_image(img: Image.Image, scale: float = 1.0):
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    words, lines, confs = [], {}, []
    for i, txt in enumerate(data["text"]):
        txt = txt.strip()
        if not txt:
            continue
        conf = float(data["conf"][i])
        if conf >= 0:
            confs.append(conf)
        x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append({"text": txt, "x0": x * scale, "top": y * scale, "x1": (x + w) * scale,
                      "bottom": (y + h) * scale, "conf": conf})
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(txt)
    text = "\n".join(" ".join(v) for v in lines.values())
    return text, words, (sum(confs) / len(confs) / 100 if confs else 0.0)


def extract_pages(path: str):
    """Return (pages, method, ms). pages = [{page, text, width, height, words, conf}]."""
    t0 = time.time()
    pages, method = [], "Text layer"
    if is_image(path):
        if not (OCR_ENABLED and TESSERACT_OK):
            raise RuntimeError("OCR is required for images but Tesseract is not available")
        img = Image.open(path).convert("RGB")
        text, words, conf = _ocr_image(img)
        pages.append({"page": 1, "text": text, "width": img.width, "height": img.height, "words": words, "conf": conf})
        method = "OCR (Tesseract)"
    else:
        with pdfplumber.open(path) as pdf:
            for i, p in enumerate(pdf.pages, start=1):
                # drop rotated watermark glyphs (e.g. "DEMO DOCUMENT") so they don't pollute the text
                p = p.filter(lambda o: o.get("object_type") != "char" or (o.get("upright", True) and o.get("size", 0) < 40))
                text = p.extract_text() or ""
                if text.strip():
                    words = [{"text": w["text"], "x0": w["x0"], "top": w["top"], "x1": w["x1"], "bottom": w["bottom"], "conf": 99}
                             for w in p.extract_words()]
                    pages.append({"page": i, "text": text, "width": float(p.width), "height": float(p.height),
                                  "words": words, "conf": 0.99})
                elif OCR_ENABLED and TESSERACT_OK:
                    img = convert_from_path(path, dpi=200, first_page=i, last_page=i)[0]
                    scale = float(p.width) / img.width
                    text, words, conf = _ocr_image(img, scale)
                    pages.append({"page": i, "text": text, "width": float(p.width), "height": float(p.height),
                                  "words": words, "conf": conf})
                    method = "Text layer + OCR"
                else:
                    pages.append({"page": i, "text": "", "width": float(p.width), "height": float(p.height), "words": [], "conf": 0})
    return pages, method, int((time.time() - t0) * 1000)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9%]", "", s.lower())


def find_bbox(page: dict, value: str):
    """Find the word sequence matching `value` on a page; return union bbox or None.
    Punctuation-only tokens (e.g. "-") are ignored on both sides."""
    target = [_norm(t) for t in value.split() if _norm(t)]
    if not target:
        return None
    words = [w for w in page.get("words", []) if _norm(w["text"])]
    normed = [_norm(w["text"]) for w in words]
    n = len(target)
    for i in range(len(words) - n + 1):
        if normed[i:i + n] == target:
            ws = words[i:i + n]
            return [min(w["x0"] for w in ws), min(w["top"] for w in ws), max(w["x1"] for w in ws), max(w["bottom"] for w in ws)]
    for i, t in enumerate(normed):  # fallback: first token contained in a word
        if target[0] in t:
            w = words[i]
            return [w["x0"], w["top"], w["x1"], w["bottom"]]
    return None


def page_count(path: str) -> int:
    if is_image(path):
        return 1
    with pdfplumber.open(path) as pdf:
        return len(pdf.pages)


def render_page(path: str, page: int, highlight=None, page_width=None, max_width=1100) -> bytes:
    """Render a page to PNG, drawing a highlight box (given in page coordinates)."""
    if is_image(path):
        img = Image.open(path).convert("RGB")
        scale = 1.0
    else:
        img = convert_from_path(path, dpi=130, first_page=page, last_page=page)[0].convert("RGB")
        with pdfplumber.open(path) as pdf:
            pw = float(pdf.pages[page - 1].width)
        scale = img.width / pw
    if highlight:
        x0, top, x1, bottom = [v * scale for v in highlight]
        pad = 6
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)
        d.rectangle([x0 - pad, top - pad, x1 + pad, bottom + pad], fill=(255, 196, 0, 90), outline=(230, 81, 0, 255), width=4)
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    if img.width > max_width:
        img = img.resize((max_width, int(img.height * max_width / img.width)))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()
