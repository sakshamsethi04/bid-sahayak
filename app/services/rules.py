"""Compliance rule engine.

Each tender requirement maps to a rule. A rule looks at the extracted fields and the
(mock) verification services and returns a status with evidence. Scoring and risk
are computed from the results. The AI/engine only RECOMMENDS; the officer decides.
"""
import math
import re
from datetime import datetime

from .verification import registry
from .verification.mock_providers import norm_name

REQUIREMENT_DEFS = {
    "gst": {"label": "GST Registration", "category": "Statutory", "weight": 15, "doc": "gst_certificate", "doc_label": "GST certificate"},
    "pan": {"label": "PAN", "category": "Statutory", "weight": 10, "doc": "pan_card", "doc_label": "PAN card"},
    "udyam": {"label": "Udyam / MSME Registration", "category": "Statutory", "weight": 10, "doc": "udyam_certificate", "doc_label": "Udyam certificate"},
    "turnover": {"label": "Average Annual Turnover", "category": "Financial", "weight": 15, "doc": "financial_statement", "doc_label": "Audited financials (3 yrs)"},
    "oem": {"label": "OEM Authorisation", "category": "Technical", "weight": 10, "doc": "oem_authorisation", "doc_label": "OEM authorisation"},
    "local_content": {"label": "Local Content (Make in India)", "category": "Technical", "weight": 15, "doc": "local_content_certificate", "doc_label": "Local content certificate"},
    "validity": {"label": "Certificate Validity (as on bid end date)", "category": "Statutory", "weight": 10, "doc": None, "doc_label": None},
    "debarment": {"label": "No Blacklisting / Debarment", "category": "Integrity", "weight": 15, "doc": None, "doc_label": "No-debarment declaration"},
}

CITIES = ["New Delhi", "Delhi", "Mumbai", "Chennai", "Kolkata", "Bengaluru", "Hyderabad", "Pune", "Ahmedabad", "Noida", "Gurugram"]


def _city(text):
    for c in CITIES:
        if c.lower() in (text or "").lower():
            return "Delhi" if c in ("New Delhi", "Delhi") else c
    return None


def _crore_value(v):
    m = re.search(r"([\d.]+)", v or "")
    return float(m.group(1)) if m else None


def _date(s):
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt)
        except (ValueError, AttributeError):
            pass
    return None


class Ctx:
    def __init__(self, docs, bidder_name, meta):
        self.docs, self.bidder, self.meta = docs, bidder_name, meta
        self.calls = []  # (provider, identifier, found, latency, source)

    def doc(self, doc_type):
        return next((d for d in self.docs if d["doc_type"] == doc_type), None)

    def field(self, doc_type, name):
        d = self.doc(doc_type)
        if not d:
            return None, None
        f = next((f for f in d["fields"] if f["name"] == name or f["name"].startswith(name)), None)
        return f, d

    def fields(self, doc_type, prefix):
        d = self.doc(doc_type)
        return ([f for f in d["fields"] if f["name"].startswith(prefix)], d) if d else ([], None)

    def ev(self, f, d, note=""):
        return {"kind": "document", "document_id": d["id"], "filename": d["filename"], "page": f["page"], "label": f["label"],
                "value": f["value"], "bbox": f.get("bbox"), "confidence": f.get("confidence"), "method": d.get("method"), "note": note}

    def lookup(self, kind, ident):
        r = registry.get(kind).lookup(ident)
        self.calls.append({"provider": registry.get(kind).name, "identifier": ident, "found": r.found, "latency_ms": r.latency_ms,
                           "source": r.source, "mode": r.mode})
        return r

    @staticmethod
    def reg_ev(r, ident):
        return {"kind": "registry", "source": r.source, "mode": r.mode, "identifier": ident, "record": r.record, "latency_ms": r.latency_ms}


def R(key, label, category, status, summary, expected, found, reason, evidence, source, severity=None, scored=True):
    sev = severity or {"VERIFIED": "ok", "CLEAR": "ok", "REVIEW": "warning", "MISSING": "critical", "FAILED": "critical"}[status]
    return {"requirement_key": key, "label": label, "category": category, "status": status, "severity": sev, "scored": scored,
            "summary": summary, "expected": expected, "found": found, "reason": reason, "evidence": evidence, "source": source}


def missing(req, doc_label, extra=""):
    return R(req["key"], req["label"], req["category"], "MISSING", f"{doc_label} not submitted",
             req["clause"], "No matching document among the uploaded files", f"Required by tender. {extra}".strip(), [], "Document check")


def rule_gst(req, c):
    f, d = c.field("gst_certificate", "gstin")
    if not f:
        return missing(req, "GST certificate")
    r = c.lookup("gst", f["value"])
    name_f, _ = c.field("gst_certificate", "legal_name")
    ev = [c.ev(f, d), c.reg_ev(r, f["value"])]
    if not r.found:
        return R("gst", req["label"], req["category"], "FAILED", "GSTIN not found", req["clause"], f["value"],
                 "GSTIN on the certificate could not be found in the GST registry.", ev, r.source)
    ok_name = norm_name(r.record["legal_name"]) == norm_name(c.bidder)
    if r.record["status"] == "Active" and ok_name:
        return R("gst", req["label"], req["category"], "VERIFIED", f"GSTIN {f['value']} · Active", "Valid, active GST registration in bidder's name",
                 f"{f['value']} · {r.record['status']} · {r.record['legal_name']}", f"Registry status Active; legal name matches bidder; {r.record['last_return']}.", ev, r.source)
    return R("gst", req["label"], req["category"], "REVIEW", "GST record needs review", "Active registration in bidder's name",
             f"{r.record['status']} · {r.record['legal_name']}", "Status or legal name differs from bid.", ev, r.source)


def rule_gst_address(c):
    g, gd = c.field("gst_certificate", "principal_place")
    o, od = c.field("bid_cover_letter", "registered_office")
    if not (g and o):
        return None
    cg, co = _city(g["value"]), _city(o["value"])
    if cg and co and cg != co:
        return R("gst_address", "GST address consistency", "Integrity", "REVIEW", f"Address mismatch: {co} vs {cg}",
                 f"Bid declares registered office in {co}", f"GST principal place of business: {g['value']}",
                 f"The bid cover letter declares the registered office in {co}, but the GST certificate (Annexure A) lists the principal place of business in {cg}. "
                 "This can be legitimate (different GST state registration) but must be confirmed before award.",
                 [c.ev(o, od, "Declared in bid"), c.ev(g, gd, "Submitted GST certificate")], "Cross-document check", scored=False)
    return None


def rule_pan(req, c):
    f, d = c.field("pan_card", "pan")
    if not f:
        return missing(req, "PAN card")
    r = c.lookup("pan", f["value"])
    ev = [c.ev(f, d), c.reg_ev(r, f["value"])]
    g, gd = c.field("gst_certificate", "gstin")
    link = ""
    if g:
        embedded = g["value"][2:12]
        link = f" PAN matches characters 3–12 of GSTIN ({embedded})." if embedded == f["value"] else f" PAN does NOT match GSTIN ({embedded})."
        ev.append(c.ev(g, gd, "GSTIN cross-check"))
    if r.found and norm_name(r.record["name"]) == norm_name(c.bidder) and "NOT" not in link:
        return R("pan", req["label"], req["category"], "VERIFIED", f"PAN {f['value']} · Valid", "PAN in bidder's name",
                 f"{f['value']} · {r.record['status']} · {r.record['holder_type']}", f"Registry: valid, name matches.{link}", ev, r.source)
    return R("pan", req["label"], req["category"], "REVIEW", "PAN needs review", "PAN in bidder's name", f["value"],
             f"Registry lookup or name match failed.{link}", ev, r.source)


def rule_udyam(req, c):
    f, d = c.field("udyam_certificate", "udyam_number")
    if not f:
        return missing(req, "Udyam certificate")
    r = c.lookup("udyam", f["value"])
    t, _ = c.field("udyam_certificate", "enterprise_type")
    ev = [c.ev(f, d)] + ([c.ev(t, d)] if t else []) + [c.reg_ev(r, f["value"])]
    if r.found and r.record["status"] == "Active" and norm_name(r.record["enterprise"]) == norm_name(c.bidder):
        return R("udyam", req["label"], req["category"], "VERIFIED", f"{f['value']} · {r.record['category']} enterprise",
                 "Valid Udyam registration (MSE)", f"{f['value']} · {r.record['category']} · {r.record['status']}",
                 f"Read by OCR from a scanned certificate (confidence {int((f.get('confidence') or 0) * 100)}%); registry confirms {r.record['category']} enterprise. MSE purchase preference applicable.",
                 ev, r.source)
    return R("udyam", req["label"], req["category"], "REVIEW", "Udyam record needs review", "Active Udyam registration", f["value"],
             "Registry lookup failed or details differ.", ev, r.source)


def rule_turnover(req, c):
    fs, d = c.fields("financial_statement", "turnover_")
    if not fs:
        return missing(req, "Audited financial statements")
    p = req["params"] or {}
    need, years = p.get("min_crore", 10), p.get("years", 3)
    vals = sorted(((f["label"].replace("Turnover ", ""), _crore_value(f["value"]), f) for f in fs), reverse=True)
    ev = [c.ev(f, d) for _, _, f in vals]
    found = ", ".join(f"{fy}: ₹{v:.2f} Cr" for fy, v, _ in vals)
    avg = sum(v for _, v, _ in vals) / len(vals)
    if len(vals) >= years:
        ok = avg >= need
        return R("turnover", req["label"], req["category"], "VERIFIED" if ok else "FAILED", f"{years}-yr average ₹{avg:.2f} Cr",
                 f"Average of last {years} FYs ≥ ₹{need:g} Cr", found, f"Average ₹{avg:.2f} Cr {'meets' if ok else 'is below'} the threshold.", ev, "Financial statement")
    latest = vals[0]
    return R("turnover", req["label"], req["category"], "REVIEW", f"Latest FY ₹{latest[1]:.2f} Cr · only {len(vals)} of {years} years",
             f"Average annual turnover of last {years} FYs ≥ ₹{need:g} Cr", found,
             f"Only {len(vals)} of {years} financial years were submitted. Latest year ({latest[0]}) is ₹{latest[1]:.2f} Cr, below the ₹{need:g} Cr threshold; "
             f"average of the available years is ₹{avg:.2f} Cr. The missing year's audited figures are needed before the criterion can be decided.",
             ev, "Financial statement", severity="warning")


def rule_oem(req, c):
    d = c.doc("oem_authorisation")
    if d:
        f, _ = c.field("oem_authorisation", "authorised_party")
        return R("oem", req["label"], req["category"], "VERIFIED", "OEM authorisation submitted", req["clause"], f["value"] if f else "Present",
                 "OEM authorisation certificate found.", [c.ev(f, d)] if f else [], "Document check")
    enc, ed = c.field("bid_cover_letter", "enclosure_oem")
    ev = [c.ev(enc, ed, "Listed as an enclosure")] if enc else []
    extra = (f"The cover letter lists it as '{enc['value']}', but no such document was found among the {len(c.docs)} uploaded files."
             if enc else "")
    r = missing(req, "OEM authorisation certificate", extra)
    r["evidence"] = ev
    r["found"] = "Not found in submission" + (" (listed in cover letter enclosures)" if enc else "")
    return r


def rule_local_content(req, c):
    f, d = c.field("local_content_certificate", "local_content")
    if not f:
        return missing(req, "Local content certificate")
    need = (req["params"] or {}).get("min_percent", 50)
    val = float(f["value"].rstrip("%"))
    issuer, _ = c.field("local_content_certificate", "issuer")
    ev = [c.ev(f, d)] + ([c.ev(issuer, d)] if issuer else [])
    ok = val >= need
    return R("local_content", req["label"], req["category"], "VERIFIED" if ok else "FAILED", f"{val:g}% local content",
             f"≥ {need:g}% local content, auditor-certified", f"{val:g}% · certified by {issuer['value'] if issuer else 'unknown'}",
             f"{val:g}% {'meets' if ok else 'is below'} the {need:g}% minimum (Class-I local supplier).", ev, "Local content certificate")


def rule_validity(req, c):
    as_on = _date((req["params"] or {}).get("as_on", "") or (c.meta.get("bid_end") or "").split(" ")[0])
    checks, ev, bad = [], [], []
    for dt, name, label in [("local_content_certificate", "valid_upto", "Local content certificate"),
                            ("oem_authorisation", "valid_upto", "OEM authorisation"), ("gst_certificate", "validity", "GST registration")]:
        f, d = c.field(dt, name)
        if not f:
            continue
        ev.append(c.ev(f, d))
        m = re.findall(r"\d{2}/\d{2}/\d{4}", f["value"])
        end = _date(m[-1]) if (m and "Not Applicable" not in f["value"]) else None
        if end is None:
            checks.append(f"{label}: no expiry")
        elif as_on and end >= as_on:
            checks.append(f"{label}: valid till {end:%d/%m/%Y}")
        else:
            bad.append(label)
            checks.append(f"{label}: EXPIRED {end:%d/%m/%Y}")
    if c.doc("udyam_certificate"):
        checks.append("Udyam: no expiry (lifetime registration)")
    status = "VERIFIED" if not bad else "FAILED"
    return R("validity", req["label"], req["category"], status, f"{len(checks)} certificates checked" + (f", {len(bad)} expired" if bad else ", all valid"),
             f"All certificates valid on {as_on:%d/%m/%Y}" if as_on else "Valid on bid end date", "; ".join(checks),
             "All submitted certificates are valid on the bid end date." if not bad else f"Expired: {', '.join(bad)}.", ev, "Document dates")


def rule_debarment(req, c):
    r = c.lookup("debarment", c.bidder)
    decl, dd = c.field("bid_cover_letter", "no_debarment_declaration")
    ev = [c.reg_ev(r, c.bidder)] + ([c.ev(decl, dd, "Self-declaration")] if decl else [])
    if r.found:
        m = r.record["matches"][0]
        return R("debarment", req["label"], req["category"], "FAILED", f"Debarred by {m['authority']}", "Not blacklisted/debarred",
                 f"Listed until {m['until']}", "Bidder appears on a debarment list.", ev, r.source)
    return R("debarment", req["label"], req["category"], "CLEAR", "No match in debarment lists", "Not blacklisted/debarred",
             f"0 matches in {r.record['lists_checked']} lists" + ("; self-declaration present" if decl else "; self-declaration missing"),
             "Bidder name not found in any debarment list" + (" and a signed no-debarment declaration is included." if decl else "."), ev, r.source,
             severity="ok" if decl else "warning")


RULES = {"gst": rule_gst, "pan": rule_pan, "udyam": rule_udyam, "turnover": rule_turnover, "oem": rule_oem,
         "local_content": rule_local_content, "validity": rule_validity, "debarment": rule_debarment}

EARN = {"VERIFIED": 1.0, "CLEAR": 1.0, "REVIEW": 0.5, "MISSING": 0.0, "FAILED": 0.0}


def evaluate(requirements, docs, bidder_name, meta):
    c = Ctx(docs, bidder_name, meta)
    results = []
    for req in requirements:
        if not req["enabled"]:
            continue
        res = RULES[req["key"]](req, c)
        res["weight"] = req["weight"]
        res["earned"] = req["weight"] * EARN[res["status"]]
        res["mandatory"] = req["mandatory"]
        results.append(res)
        if req["key"] == "gst":
            extra = rule_gst_address(c)
            if extra:
                extra["weight"] = extra["earned"] = 0
                extra["mandatory"] = False
                results.append(extra)
    total = sum(r["weight"] for r in results if r["scored"])
    earned = sum(r["earned"] for r in results if r["scored"])
    score = math.floor(100 * earned / total) if total else 0
    critical = [r for r in results if r["severity"] == "critical"]
    warnings = [r for r in results if r["severity"] == "warning"]
    if score < 60 or len(critical) >= 2 or any(r["status"] == "FAILED" and r["requirement_key"] == "debarment" for r in results):
        risk = "HIGH"
    elif critical or len(warnings) >= 2 or score < 90:
        risk = "MEDIUM"
    else:
        risk = "LOW"
    return results, score, risk, c.calls


def recommendation(results, score, risk, bidder):
    ok = [r for r in results if r["scored"] and r["status"] in ("VERIFIED", "CLEAR")]
    scored = [r for r in results if r["scored"]]
    crit = [r for r in results if r["severity"] == "critical"]
    warn = [r for r in results if r["severity"] == "warning"]
    parts = [f"{bidder} satisfies {len(ok)} of {len(scored)} tender requirements (compliance {score}%, risk {risk})."]
    if crit:
        parts.append("Critical: " + "; ".join(f"{r['label']} ({r['summary']})" for r in crit) + ".")
    if warn:
        parts.append("Needs manual verification: " + "; ".join(f"{r['label']} ({r['summary']})" for r in warn) + ".")
    if crit:
        action = "Suggested next step: request clarification and the missing documents from the bidder before a final decision (Special condition 5.4 permits clarification)."
    elif warn:
        action = "Suggested next step: officer to verify the flagged items; bidder can be qualified once confirmed."
    else:
        action = "Suggested next step: bidder appears eligible; officer may qualify after review."
    parts.append(action)
    return " ".join(parts), ("CLARIFY" if crit or warn else "QUALIFY")
