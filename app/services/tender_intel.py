"""Tender intelligence: turns tender text into metadata + an eligibility checklist.

Deterministic clause detection (regex over the tender's own text) so the demo never
depends on an external API. Each requirement keeps the clause text and page it came
from, so the officer can see *why* it is on the checklist.
"""
import re

from .rules import REQUIREMENT_DEFS

META_PATTERNS = {
    "bid_number": r"Bid Number\s+(GEM/\d{4}/B/\d+)",
    "dated": r"Dated\s+(\d{2}-\d{2}-\d{4})",
    "bid_end": r"Bid End Date/Time\s+(\d{2}-\d{2}-\d{4}[ \d:]*)",
    "ministry": r"Ministry\s+(Ministry of [^\n]+)",
    "organisation": r"Organisation\s+([^\n]+)",
    "item": r"Item Category\s+([^\n]+)",
    "quantity": r"Total Quantity\s+(\d+)",
    "estimated_value": r"Estimated Bid Value\s+([^\n]+)",
    "emd": r"EMD Amount\s+([^\n]+)",
    "bid_type": r"Type of Bid\s+([^\n]+)",
}

# clause detectors: key -> regex on the clause text
CLAUSE_DETECTORS = {
    "gst": r"GST\s+Registration|GSTIN",
    "pan": r"\bPAN\b",
    "udyam": r"Udyam|MSME|Micro and Small",
    "turnover": r"turnover",
    "oem": r"OEM\s+authori[sz]ation",
    "local_content": r"local content",
    "validity": r"valid as on the bid end date|Validity of Documents",
    "debarment": r"blacklist|debar",
}


def _split_clauses(pages):
    """Yield (number, text, page) for numbered clauses like '4.4 ...'."""
    out = []
    for p in pages:
        parts = re.split(r"\n(?=\d\.\d+\s)", "\n" + p["text"])
        for part in parts:
            m = re.match(r"(\d\.\d+)\s+(.*)", part.strip(), re.S)
            if m:
                out.append((m.group(1), " ".join(m.group(2).split()), p["page"]))
    return out


def _money_crore(text):
    m = re.search(r"Rs\.?\s*([\d.,]+)\s*Crore", text, re.I)
    return float(m.group(1).replace(",", "")) if m else None


def analyze(pages):
    full = "\n".join(p["text"] for p in pages)
    meta = {k: (m.group(1).strip() if (m := re.search(pat, full)) else None) for k, pat in META_PATTERNS.items()}

    clauses = _split_clauses(pages)
    requirements, used = [], set()
    for num, text, page in clauses:
        for key, pat in CLAUSE_DETECTORS.items():
            if key in used or not re.search(pat, text, re.I):
                continue
            # the PAN detector must not fire on the GST clause etc.
            if key == "pan" and "GST" in text:
                continue
            if key == "udyam" and "turnover" in text.lower():
                continue
            d = REQUIREMENT_DEFS[key]
            params = {}
            if key == "turnover":
                params = {"min_crore": _money_crore(text) or 10.0,
                          "years": 3 if re.search(r"three|3\s*financial", text, re.I) else 1,
                          "basis": "average" if "average" in text.lower() else "latest"}
            if key == "local_content":
                m = re.search(r"(\d+)\s*%", text)
                params = {"min_percent": float(m.group(1)) if m else 50.0}
            if key == "validity":
                params = {"as_on": (meta.get("bid_end") or "").split(" ")[0]}
            label = d["label"]
            if key == "turnover":
                label = f"Avg. Annual Turnover ≥ ₹{params['min_crore']:g} Cr ({params['years']} yrs)"
            if key == "local_content":
                label = f"Local Content ≥ {params['min_percent']:g}% (Make in India)"
            requirements.append({
                "key": key, "label": label, "category": d["category"], "weight": d["weight"],
                "mandatory": True, "params": params, "clause": f"Clause {num}: {text}", "clause_page": page,
            })
            used.add(key)
            break

    special = [c for c in clauses if c[0].startswith("5.")]
    docs_needed = sorted({REQUIREMENT_DEFS[r["key"]]["doc_label"] for r in requirements if REQUIREMENT_DEFS[r["key"]].get("doc_label")})
    fin = [r for r in requirements if r["category"] == "Financial"]
    steps = [
        {"label": "Tender identified", "detail": f"{meta.get('bid_number') or 'Unknown bid no.'} · {len(pages)} pages · {meta.get('ministry') or ''}"},
        {"label": "Eligibility criteria extracted", "detail": f"{len(requirements)} criteria from Section 4"},
        {"label": "Financial requirements extracted",
         "detail": "; ".join([r["label"] for r in fin] + ([f"EMD {meta['emd']}"] if meta.get("emd") else []))},
        {"label": "Documentation requirements extracted", "detail": f"{len(docs_needed)} documents: " + ", ".join(docs_needed)},
        {"label": "Special conditions identified", "detail": f"{len(special)} conditions (delivery, performance security, warranty, clarification)"},
    ]
    order = list(REQUIREMENT_DEFS.keys())
    requirements.sort(key=lambda r: order.index(r["key"]))
    return meta, requirements, steps
