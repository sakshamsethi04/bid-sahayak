"""BidSahayak API (FastAPI). Also serves the built React app from frontend/dist."""
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import models as m
from .config import DEMO_DIR, FRONTEND_DIST, OCR_ENABLED, llm_enabled
from .db import get_db, init_db
from .services import documents, pipeline
from .services.rules import REQUIREMENT_DEFS
from .services.verification import registry

app = FastAPI(title="BidSahayak API", version="0.1.0-poc")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
init_db()


def officer_name(x_officer: str = Header(default="Procurement Officer")):
    return x_officer


def get_case(db, case_id) -> m.Case:
    case = db.get(m.Case, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    return case


# ------------------------------------------------------------------ serializers
def ser_case(c: m.Case, full=True):
    out = {
        "id": c.id, "reference": c.reference, "status": c.status, "bidder_name": c.bidder_name,
        "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        "score": c.score, "risk": c.risk, "decision": c.decision, "decision_remarks": c.decision_remarks,
        "decided_by": c.decided_by, "decided_at": c.decided_at.isoformat() if c.decided_at else None,
        "tender": ({"filename": c.tender.filename, "pages": c.tender.pages, "meta": c.tender.meta, "analysis": c.tender.analysis}
                   if c.tender else None),
        "counts": {
            "requirements": len(c.requirements), "documents": len(c.documents),
            "critical": sum(1 for r in c.results if r.severity == "critical"),
            "warnings": sum(1 for r in c.results if r.severity == "warning"),
        },
    }
    if not full:
        return out
    present = {d.doc_type for d in c.documents}
    out["requirements"] = [{"id": r.id, "key": r.key, "label": r.label, "category": r.category, "mandatory": r.mandatory,
                            "enabled": r.enabled, "weight": r.weight, "params": r.params, "clause": r.clause, "clause_page": r.clause_page,
                            "expected_document": REQUIREMENT_DEFS[r.key]["doc_label"]} for r in c.requirements]
    out["documents"] = [{"id": d.id, "filename": d.filename, "mime": d.mime, "doc_type": d.doc_type, "doc_type_label": d.doc_type_label,
                         "pages": d.pages, "method": d.method, "status": d.status, "processing_ms": d.processing_ms,
                         "fields": [{"id": f.id, "name": f.name, "label": f.label, "value": f.value, "page": f.page,
                                     "confidence": f.confidence, "bbox": f.bbox} for f in d.fields]} for d in c.documents]
    out["missing_documents"] = [{"requirement": r.label, "document": REQUIREMENT_DEFS[r.key]["doc_label"], "clause": r.clause.split(":")[0]}
                                for r in c.requirements if r.enabled and REQUIREMENT_DEFS[r.key]["doc"]
                                and REQUIREMENT_DEFS[r.key]["doc"] not in present and c.documents and c.status != "DOCUMENTS"]
    out["results"] = [{"id": r.id, "key": r.requirement_key, "label": r.label, "category": r.category, "status": r.status,
                       "severity": r.severity, "scored": r.scored, "weight": r.weight, "earned": r.earned, "summary": r.summary,
                       "expected": r.expected, "found": r.found, "reason": r.reason, "source": r.source, "evidence": r.evidence}
                      for r in c.results]
    out["recommendation"] = c.recommendation
    out["recommendation_source"] = c.recommendation_source
    out["audit"] = [{"id": a.id, "ts": a.ts.isoformat(), "actor": a.actor, "action": a.action, "result": a.result, "detail": a.detail,
                     "hash": a.hash} for a in c.audit]
    out["audit_integrity"] = pipeline.verify_chain(c)
    out["communication"] = c.communication
    return out


# ------------------------------------------------------------------ routes
@app.get("/api/health")
def health():
    return {"ok": True, "ocr": documents.TESSERACT_OK and OCR_ENABLED, "llm": llm_enabled(), "verification_mode": "mock"}


@app.get("/api/system")
def system():
    return {
        "ocr": {"engine": "Tesseract", "available": documents.TESSERACT_OK and OCR_ENABLED},
        "llm": {"enabled": llm_enabled(), "note": "Optional. Deterministic rule engine is used when no key is set."},
        "integrations": registry.describe(),
    }


@app.get("/api/cases")
def list_cases(db: Session = Depends(get_db)):
    return [ser_case(c, full=False) for c in db.query(m.Case).order_by(m.Case.id.desc()).all()]


@app.post("/api/cases")
def create_case(db: Session = Depends(get_db), officer: str = Depends(officer_name)):
    return ser_case(pipeline.new_case(db, officer))


@app.get("/api/cases/{case_id}")
def read_case(case_id: int, db: Session = Depends(get_db)):
    return ser_case(get_case(db, case_id))


@app.delete("/api/cases/{case_id}")
def delete_case(case_id: int, db: Session = Depends(get_db)):
    db.delete(get_case(db, case_id))
    db.commit()
    return {"ok": True}


async def _save_upload(up: UploadFile) -> Path:
    suffix = Path(up.filename).suffix
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(await up.read())
    tmp.close()
    return Path(tmp.name)


@app.post("/api/cases/{case_id}/tender")
async def upload_tender(case_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), officer: str = Depends(officer_name)):
    case = get_case(db, case_id)
    tmp = await _save_upload(file)
    pipeline.ingest_tender(db, case, tmp, Path(file.filename).name, officer)
    return ser_case(case)


@app.post("/api/cases/{case_id}/tender/demo")
def demo_tender(case_id: int, db: Session = Depends(get_db), officer: str = Depends(officer_name)):
    case = get_case(db, case_id)
    pipeline.run_demo_tender(db, case, officer)
    return ser_case(case)


class ReqUpdate(BaseModel):
    items: list[dict]


@app.put("/api/cases/{case_id}/requirements")
def update_reqs(case_id: int, body: ReqUpdate, db: Session = Depends(get_db), officer: str = Depends(officer_name)):
    case = get_case(db, case_id)
    pipeline.update_requirements(db, case, body.items, officer)
    return ser_case(case)


@app.post("/api/cases/{case_id}/documents")
async def upload_docs(case_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db), officer: str = Depends(officer_name)):
    case = get_case(db, case_id)
    saved = [(await _save_upload(f), Path(f.filename).name) for f in files]
    pipeline.add_documents(db, case, saved, officer)
    return ser_case(case)


@app.post("/api/cases/{case_id}/documents/demo")
def demo_docs(case_id: int, db: Session = Depends(get_db), officer: str = Depends(officer_name)):
    case = get_case(db, case_id)
    for d in list(case.documents):
        db.delete(d)
    db.flush()
    pipeline.add_documents(db, case, [(p, p.name) for p in pipeline.demo_bidder_files()], officer)
    return ser_case(case)


@app.delete("/api/documents/{doc_id}")
def delete_doc(doc_id: int, db: Session = Depends(get_db)):
    d = db.get(m.Document, doc_id)
    if not d:
        raise HTTPException(404)
    db.delete(d)
    db.commit()
    return {"ok": True}


@app.post("/api/cases/{case_id}/process")
def process(case_id: int, db: Session = Depends(get_db)):
    case = get_case(db, case_id)
    pipeline.process_documents(db, case)
    return ser_case(case)


@app.post("/api/cases/{case_id}/verify")
def verify(case_id: int, db: Session = Depends(get_db)):
    case = get_case(db, case_id)
    if not case.tender:
        raise HTTPException(400, "Upload a tender first")
    pipeline.verify(db, case)
    return ser_case(case)


class Decision(BaseModel):
    decision: str
    remarks: str = ""


@app.post("/api/cases/{case_id}/decision")
def decision(case_id: int, body: Decision, db: Session = Depends(get_db), officer: str = Depends(officer_name)):
    if body.decision not in ("QUALIFY", "CLARIFY", "REJECT"):
        raise HTTPException(400, "Invalid decision")
    if len(body.remarks.strip()) < 5:
        raise HTTPException(400, "Remarks are mandatory for the audit record")
    case = get_case(db, case_id)
    pipeline.decide(db, case, body.decision, body.remarks.strip(), officer)
    return ser_case(case)


@app.get("/api/documents/{doc_id}/file")
def doc_file(doc_id: int, db: Session = Depends(get_db)):
    d = db.get(m.Document, doc_id)
    if not d:
        raise HTTPException(404)
    return FileResponse(d.path, filename=d.filename, content_disposition_type="inline")


@app.get("/api/documents/{doc_id}/page/{page}")
def doc_page(doc_id: int, page: int, hl: str | None = None, db: Session = Depends(get_db)):
    d = db.get(m.Document, doc_id)
    if not d:
        raise HTTPException(404)
    box = [float(v) for v in hl.split(",")] if hl else None
    return Response(documents.render_page(d.path, page, box), media_type="image/png",
                    headers={"Cache-Control": "max-age=3600"})


@app.get("/api/cases/{case_id}/tender/page/{page}")
def tender_page(case_id: int, page: int, db: Session = Depends(get_db)):
    case = get_case(db, case_id)
    return Response(documents.render_page(case.tender.path, page), media_type="image/png")


@app.get("/api/cases/{case_id}/tender/file")
def tender_file(case_id: int, db: Session = Depends(get_db)):
    case = get_case(db, case_id)
    return FileResponse(case.tender.path, filename=case.tender.filename, content_disposition_type="inline")


@app.get("/api/demo/files")
def demo_files():
    return {"tender": "Tender_GEM-2026-B-5873214.pdf", "bidder": [p.name for p in pipeline.demo_bidder_files()]}


@app.get("/api/demo/bundle.zip")
def demo_bundle():
    """All demo files, so the presenter can drag-and-drop them manually (proves nothing is pre-baked)."""
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(DEMO_DIR / "Tender_GEM-2026-B-5873214.pdf", "tender/Tender_GEM-2026-B-5873214.pdf")
        for p in pipeline.demo_bidder_files():
            z.write(p, f"bidder_ABC_Engineering/{p.name}")
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": "attachment; filename=BidSahayak_demo_files.zip"})


@app.get("/api/documents/{doc_id}/text")
def doc_text(doc_id: int, db: Session = Depends(get_db)):
    d = db.get(m.Document, doc_id)
    if not d:
        raise HTTPException(404)
    return {"filename": d.filename, "method": d.method, "pages": [{"page": p["page"], "text": p["text"], "conf": p.get("conf")} for p in (d.page_text or [])]}


# ------------------------------------------------------------------ frontend
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = FRONTEND_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
