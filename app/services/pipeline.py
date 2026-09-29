"""Orchestrates a verification case: tender -> checklist -> documents -> extraction
-> verification -> report -> officer decision, writing the audit trail as it goes."""
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from .. import models as m
from ..config import DEMO_DIR, UPLOAD_DIR
from . import documents, extraction, llm, rules, tender_intel

SYSTEM = "System"


class Clock:
    """Audit timestamps. In demo mode we space events a few seconds apart so the
    trail reads like a real session instead of 20 events in the same second."""
    def __init__(self, case):
        last = case.audit[-1].ts if case.audit else datetime.now()
        self.t = max(last, datetime.now())

    def tick(self, seconds=2):
        self.t = self.t + timedelta(seconds=seconds)
        return self.t


def audit(db, case, actor, action, result, detail="", ts=None):
    if ts is None:  # keep the trail monotonic even after demo-spaced events
        last = max((e.ts for e in case.audit), default=None)
        ts = max(datetime.now(), last + timedelta(seconds=1)) if last else datetime.now()
    case.audit.append(m.AuditEvent(actor=actor, action=action, result=result, detail=detail, ts=ts or datetime.now()))


def new_case(db: Session, officer: str):
    n = db.query(m.Case).count() + 1
    case = m.Case(reference=f"BSV-2026-{1040 + n:04d}")
    db.add(case)
    db.flush()
    audit(db, case, officer, "Verification case created", case.reference)
    seal(case)
    db.commit()
    return case


def _store(case, src: Path, filename: str) -> Path:
    dest_dir = UPLOAD_DIR / case.reference
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    shutil.copyfile(src, dest)
    return dest


def ingest_tender(db, case, path: Path, filename: str, officer: str):
    clk = Clock(case)
    stored = _store(case, path, filename)
    audit(db, case, officer, "Tender uploaded", filename, ts=clk.tick(0))
    pages, method, ms = documents.extract_pages(str(stored))
    meta, reqs, steps = tender_intel.analyze(pages)
    if case.tender:
        db.delete(case.tender)
    for r in list(case.requirements):
        db.delete(r)
    db.flush()
    case.tender = m.Tender(filename=filename, path=str(stored), pages=len(pages), meta=meta, analysis=steps)
    case.requirements = [m.Requirement(position=i, **r) for i, r in enumerate(reqs)]
    case.status = "CHECKLIST"
    audit(db, case, "System · Tender Intelligence", "Tender analysed", f"{meta.get('bid_number')} · {len(pages)} pages · {method}",
          f"{ms} ms", ts=clk.tick(3))
    audit(db, case, "System · Tender Intelligence", "Eligibility checklist generated", f"{len(reqs)} criteria extracted",
          ", ".join(r["label"] for r in reqs), ts=clk.tick(1))
    seal(case)
    db.commit()
    db.refresh(case)
    return case


def update_requirements(db, case, items, officer):
    by_id = {r.id: r for r in case.requirements}
    changes = []
    for it in items:
        r = by_id.get(it["id"])
        if not r:
            continue
        for k in ("enabled", "mandatory", "weight", "params", "label"):
            if k in it and it[k] != getattr(r, k):
                changes.append(f"{r.key}.{k}: {getattr(r, k)} → {it[k]}")
                setattr(r, k, it[k])
    audit(db, case, officer, "Checklist reviewed", "Approved" + (f" with {len(changes)} change(s)" if changes else " without changes"),
          "; ".join(changes))
    case.status = "DOCUMENTS"
    seal(case)
    db.commit()


def add_documents(db, case, files, officer):
    """files: list of (Path, filename)."""
    clk = Clock(case)
    for src, name in files:
        stored = _store(case, src, name)
        case.documents.append(m.Document(filename=name, path=str(stored),
                          mime="image" if documents.is_image(name) else "application/pdf", pages=documents.page_count(str(stored))))
    audit(db, case, officer, "Bidder documents uploaded", f"{len(files)} files", ", ".join(n for _, n in files), ts=clk.tick(1))
    case.status = "DOCUMENTS"
    seal(case)
    db.commit()
    db.refresh(case)


def process_documents(db, case):
    clk = Clock(case)
    for d in case.documents:
        if d.status == "PROCESSED":
            continue
        try:
            pages, method, ms = documents.extract_pages(d.path)
            d.page_text, d.method, d.processing_ms, d.pages = pages, method, ms, len(pages)
            d.doc_type, d.doc_type_label = extraction.classify(pages, d.filename)
            d.fields = [m.ExtractedField(**f) for f in extraction.extract_fields(d.doc_type, pages)]
            d.status = "PROCESSED"
            actor = "System · OCR Engine (Tesseract)" if "OCR" in method else "System · Document Parser"
            audit(db, case, actor, f"Extracted {d.filename}", f"{d.doc_type_label} · {method}", f"{ms} ms", ts=clk.tick(2))
        except Exception as e:
            d.status = "FAILED"
            audit(db, case, "System · Document Parser", f"Failed to process {d.filename}", "Error", str(e), ts=clk.tick(1))
    db.flush()
    # bidder name from the cover letter, else GST legal name
    name = None
    for d in case.documents:
        for f in d.fields:
            if f.name == "company_name":
                name = f.value
    if not name:
        for d in case.documents:
            for f in d.fields:
                if f.name == "legal_name":
                    name = f.value.title()
    case.bidder_name = name or "Unknown bidder"
    present = {d.doc_type for d in case.documents}
    for r in case.requirements:
        need = rules.REQUIREMENT_DEFS[r.key]["doc"]
        if r.enabled and need and need not in present:
            audit(db, case, "System · Document Parser", "Expected document not found", rules.REQUIREMENT_DEFS[r.key]["doc_label"],
                  f"Required by {r.clause.split(':')[0]}", ts=clk.tick(1))
    case.status = "EXTRACTED"
    audit(db, case, "System · Extraction Engine", "Extraction completed",
          f"{sum(len(d.fields) for d in case.documents)} fields from {len(case.documents)} documents", ts=clk.tick(1))
    seal(case)
    db.commit()
    db.refresh(case)


def doc_payload(d):
    return {"id": d.id, "filename": d.filename, "doc_type": d.doc_type, "method": d.method,
            "fields": [{"name": f.name, "label": f.label, "value": f.value, "page": f.page, "confidence": f.confidence, "bbox": f.bbox}
                       for f in d.fields]}


def verify(db, case):
    clk = Clock(case)
    reqs = [{"key": r.key, "label": r.label, "category": r.category, "weight": r.weight, "mandatory": r.mandatory,
             "enabled": r.enabled, "params": r.params, "clause": r.clause} for r in case.requirements]
    docs = [doc_payload(d) for d in case.documents if d.status == "PROCESSED"]
    results, score, risk, calls = rules.evaluate(reqs, docs, case.bidder_name, case.tender.meta if case.tender else {})
    for c in calls:
        audit(db, case, f"{c['source']} ({c['mode']})", f"Lookup {c['identifier']}", "Record found" if c["found"] else "No record",
              f"{c['provider']} · {c['latency_ms']} ms", ts=clk.tick(1))
    case.results = []
    db.flush()
    for i, r in enumerate(results):
        case.results.append(m.CheckResult(position=i, **{k: v for k, v in r.items() if k != "mandatory"}))
        audit(db, case, "System · Rule Engine", f"{r['label']}", r["status"], r["summary"], ts=clk.tick(1))
    text, _ = rules.recommendation(results, score, risk, case.bidder_name)
    case.recommendation, case.recommendation_source = llm.phrase_recommendation(text)
    case.score, case.risk, case.status = score, risk, "VERIFIED"
    audit(db, case, "System · Rule Engine", "Compliance report generated", f"{score}% · Risk {risk}",
          f"Recommendation source: {case.recommendation_source}", ts=clk.tick(1))
    seal(case)
    db.commit()
    db.refresh(case)


def decide(db, case, decision, remarks, officer):
    labels = {"QUALIFY": "Qualified", "CLARIFY": "Clarification requested", "REJECT": "Rejected"}
    case.decision, case.decision_remarks, case.decided_by, case.decided_at = decision, remarks, officer, datetime.now()
    case.status = "DECIDED"
    case.communication = draft_letter(case, decision, remarks, officer)
    audit(db, case, officer, "Officer decision", labels[decision], remarks)
    audit(db, case, "System · Communication", "Bidder communication drafted", labels[decision], "Awaiting officer to send")
    seal(case)
    db.commit()


def run_demo_tender(db, case, officer):
    f = DEMO_DIR / "Tender_GEM-2026-B-5873214.pdf"
    return ingest_tender(db, case, f, f.name, officer)


def demo_bidder_files():
    return sorted((DEMO_DIR / "bidder").iterdir())


# ------------------------------------------------------------------ audit integrity
import hashlib  # noqa: E402


def _digest(prev, e):
    payload = "|".join([prev, e.ts.isoformat(timespec="microseconds"), e.actor or "", e.action or "", e.result or "", e.detail or ""])
    return hashlib.sha256(payload.encode()).hexdigest()


def seal(case):
    """Hash-chain any unsealed audit events (append-only, tamper-evident)."""
    sealed = sorted([e for e in case.audit if e.hash], key=lambda x: x.id)
    prev = sealed[-1].hash if sealed else ""
    for e in [e for e in case.audit if not e.hash]:  # in append order
        e.prev_hash, e.hash = prev, _digest(prev, e)
        prev = e.hash


def verify_chain(case):
    prev, n = "", 0
    for e in sorted(case.audit, key=lambda x: x.id):
        if e.prev_hash != prev or e.hash != _digest(prev, e):
            return {"valid": False, "events": len(case.audit), "broken_at": e.id}
        prev, n = e.hash, n + 1
    return {"valid": True, "events": n, "head": prev}


# ------------------------------------------------------------------ bidder communication
def draft_letter(case, decision, remarks, officer):
    meta = case.tender.meta if case.tender else {}
    crit = [r for r in case.results if r.severity == "critical"]
    warn = [r for r in case.results if r.severity == "warning"]
    today = datetime.now().strftime("%d-%m-%Y")
    head = [f"To: {case.bidder_name}", f"Ref: {meta.get('bid_number', '')} · Verification case {case.reference}", f"Date: {today}", ""]
    if decision == "QUALIFY":
        body = ["Subject: Technical evaluation — qualified", "",
                "Your bid has been found technically qualified on the documents submitted. This is subject to the terms of the bid document."]
    else:
        subj = "Request for clarification / additional documents" if decision == "CLARIFY" else "Technical evaluation — bid not qualified"
        body = [f"Subject: {subj}", "", "During technical evaluation of your bid, the following points were observed:", ""]
        i = 1
        for r in crit + warn:
            clause = next((q.clause.split(":")[0] for q in case.requirements if q.key == r.requirement_key), "")
            body.append(f"{i}. {r.label}{f' ({clause})' if clause else ''}: {r.reason}")
            i += 1
        body.append("")
        if decision == "CLARIFY":
            reply_by = (datetime.now() + timedelta(days=5)).strftime("%d-%m-%Y")
            body.append(f"You are requested to submit the above documents / clarification by {reply_by}, as permitted under Special Condition 5.4.")
        else:
            body.append("Accordingly, the bid is not qualified for the next stage of evaluation.")
    body += ["", f"Officer remarks: {remarks}", "", officer, meta.get("organisation", ""),
             "", "[Draft generated by BidSahayak from the verification report. Review before sending.]"]
    return "\n".join(head + body)
