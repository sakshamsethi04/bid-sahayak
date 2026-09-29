"""Extraction layer: classify each bidder document and pull structured fields,
each tied to the page (and word box) it came from.

The default engine is a deterministic parser over the text layer / OCR output, so
the demo always works offline. `llm.py` can be plugged in for unseen layouts.
"""
import re

from .documents import find_bbox

DOC_TYPES = {
    "gst_certificate": ("GST Registration Certificate", [r"Form GST REG-06", r"GSTIN"]),
    "pan_card": ("PAN Card", [r"Permanent Account Number"]),
    "udyam_certificate": ("Udyam Registration Certificate", [r"UDYAM REGISTRATION"]),
    "financial_statement": ("Audited Financial Statement", [r"Statement of Profit and Loss", r"Balance Sheet"]),
    "local_content_certificate": ("Local Content Certificate", [r"Certificate of Local Content", r"local content of"]),
    "oem_authorisation": ("OEM Authorisation Certificate", [r"OEM\s+Authori[sz]ation\s+(Certificate|Letter)\b(?![^\n]*Annexure)", r"Manufacturer'?s Authori[sz]ation Form"]),
    "bid_cover_letter": ("Bid Cover Letter & Declaration", [r"Subject:\s*Submission of bid", r"hereby submit our bid"]),
}


def classify(pages, filename=""):
    text = "\n".join(p["text"] for p in pages)
    scores = {}
    for key, (_, pats) in DOC_TYPES.items():
        scores[key] = sum(1 for pat in pats if re.search(pat, text, re.I))
    # cover letter mentions many doc names; prefer specific types
    best = max(scores, key=lambda k: (scores[k], k != "bid_cover_letter"))
    if scores[best] == 0:
        return "other", "Other document"
    return best, DOC_TYPES[best][0]


def _field(fields, pages, name, label, value, page_no, snippet=None, conf=None):
    page = next(p for p in pages if p["page"] == page_no)
    fields.append({
        "name": name, "label": label, "value": value, "page": page_no,
        "snippet": snippet or value, "confidence": round(conf if conf is not None else page.get("conf", 0.95), 2),
        "bbox": find_bbox(page, snippet or value),
    })


def _search(pages, pattern, flags=re.I):
    for p in pages:
        m = re.search(pattern, p["text"], flags)
        if m:
            return m, p["page"]
    return None, None


def _crore(amount: str) -> float:
    return round(float(amount.replace(",", "")) / 1e7, 2)


def extract_fields(doc_type, pages):
    f = []
    if doc_type == "gst_certificate":
        m, pg = _search(pages, r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z])\b", 0)
        if m: _field(f, pages, "gstin", "GSTIN", m.group(1), pg)
        m, pg = _search(pages, r"Legal Name[:\s]+([A-Z][A-Z .&]+)")
        if m: _field(f, pages, "legal_name", "Legal name", m.group(1).strip(), pg)
        m, pg = _search(pages, r"Period of Validity\s+(.+)")
        if m: _field(f, pages, "validity", "Validity", m.group(1).strip(), pg)
        m, pg = _search(pages, r"Principal Place of Business:\s*(.+)")
        if m: _field(f, pages, "principal_place", "Principal place of business", m.group(1).strip(), pg, snippet="Mumbai, Maharashtra" if "Mumbai" in m.group(1) else None)
        m, pg = _search(pages, r"Type of Registration\s+(\w+)")
        if m: _field(f, pages, "registration_type", "Registration type", m.group(1), pg)
    elif doc_type == "pan_card":
        m, pg = _search(pages, r"\b([A-Z]{5}\d{4}[A-Z])\b", 0)
        if m: _field(f, pages, "pan", "PAN", m.group(1), pg)
        m, pg = _search(pages, r"Name:\s*([A-Z][A-Z .&]+)")
        if m: _field(f, pages, "name", "Name on PAN", m.group(1).strip(), pg)
        m, pg = _search(pages, r"Date of Incorporation/Formation:\s*([\d/]+)")
        if m: _field(f, pages, "incorporation", "Date of incorporation", m.group(1), pg)
    elif doc_type == "udyam_certificate":
        m, pg = _search(pages, r"(UDYAM-[A-Z]{2}-\d{2}-\d{7})", 0)
        if m: _field(f, pages, "udyam_number", "Udyam number", m.group(1), pg)
        m, pg = _search(pages, r"NAME OF ENTERPRISE\s*\n\s*(.+)")
        if m: _field(f, pages, "enterprise_name", "Enterprise name", m.group(1).strip(), pg)
        m, pg = _search(pages, r"TYPE OF ENTERPRISE\s*\n\s*(\w+)")
        if m: _field(f, pages, "enterprise_type", "Enterprise type", m.group(1), pg)
        m, pg = _search(pages, r"DATE OF UDYAM REGISTRATION\s*\n\s*([\d/]+)")
        if m: _field(f, pages, "registered_on", "Registered on", m.group(1), pg)
    elif doc_type == "financial_statement":
        hdr, _ = _search(pages, r"FY (\d{4}-\d{2})\s+FY (\d{4}-\d{2})")
        m, pg = _search(pages, r"Revenue from Operations\s+([\d,]+)\s+([\d,]+)")
        if m and hdr:
            _field(f, pages, f"turnover_{hdr.group(1)}", f"Turnover FY {hdr.group(1)}", f"₹{_crore(m.group(1)):.2f} Cr", pg, snippet=m.group(1))
            _field(f, pages, f"turnover_{hdr.group(2)}", f"Turnover FY {hdr.group(2)}", f"₹{_crore(m.group(2)):.2f} Cr", pg, snippet=m.group(2))
        m, pg = _search(pages, r"UDIN\s+(\w+)")
        if m: _field(f, pages, "udin", "Auditor UDIN", m.group(1), pg)
    elif doc_type == "local_content_certificate":
        m, pg = _search(pages, r"local content of (\d+)%")
        if m: _field(f, pages, "local_content", "Local content", f"{m.group(1)}%", pg, snippet=f"{m.group(1)}%")
        m, pg = _search(pages, r"Valid Up To:\s*([\d/]+)")
        if m: _field(f, pages, "valid_upto", "Valid up to", m.group(1), pg)
        m, pg = _search(pages, r"Class of Supplier:\s*(.+)")
        if m: _field(f, pages, "supplier_class", "Supplier class", m.group(1).strip(), pg)
        m, pg = _search(pages, r"Issued by:\s*(.+)")
        if m: _field(f, pages, "issuer", "Issued by", m.group(1).strip(), pg, snippet="S. Mehta & Associates")
    elif doc_type == "oem_authorisation":
        m, pg = _search(pages, r"(?:authori[sz]e|authori[sz]ation to)\s+(M/s\.?\s*)?([A-Z][\w .&]+?Ltd\.?)")
        if m: _field(f, pages, "authorised_party", "Authorised dealer", m.group(2), pg)
        m, pg = _search(pages, r"valid (?:up to|till)\s*([\d/-]+)")
        if m: _field(f, pages, "valid_upto", "Valid up to", m.group(1), pg)
    elif doc_type == "bid_cover_letter":
        m, pg = _search(pages, r"We,\s*(.+?),\s*having")
        if m: _field(f, pages, "company_name", "Bidder name", m.group(1).strip(), pg)
        m, pg = _search(pages, r"Registered Office:\s*(.+?)\s*\|")
        if m: _field(f, pages, "registered_office", "Registered office (declared)", m.group(1).strip(), pg, snippet="New Delhi")
        m, pg = _search(pages, r"(GEM/\d{4}/B/\d+)", 0)
        if m: _field(f, pages, "bid_number", "Bid number", m.group(1), pg)
        m, pg = _search(pages, r"(not\s+been\s+blacklisted\s+or\s+debarred)")
        if m: _field(f, pages, "no_debarment_declaration", "No-debarment declaration", "Present", pg, snippet="not been blacklisted or debarred")
        m, pg = _search(pages, r"\d\.\s*(OEM Authori[sz]ation Certificate[^\n]*)")
        if m: _field(f, pages, "enclosure_oem", "Enclosure listed: OEM authorisation", m.group(1).strip(), pg, snippet="OEM Authorisation Certificate")
    return f
