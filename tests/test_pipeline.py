"""End-to-end test of the demo scenario through the API. Run: python -m pytest -q"""
import os
import tempfile

os.environ["BIDSAHAYAK_DATA_DIR"] = tempfile.mkdtemp()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
H = {"X-Officer": "Test Officer"}


def test_demo_flow():
    case = client.post("/api/cases", headers=H).json()
    cid = case["id"]
    c = client.post(f"/api/cases/{cid}/tender/demo", headers=H).json()
    keys = [r["key"] for r in c["requirements"]]
    assert keys == ["gst", "pan", "udyam", "turnover", "oem", "local_content", "validity", "debarment"]
    assert c["tender"]["meta"]["bid_number"] == "GEM/2026/B/5873214"
    turnover = next(r for r in c["requirements"] if r["key"] == "turnover")
    assert turnover["params"]["min_crore"] == 10.0 and turnover["params"]["years"] == 3

    client.put(f"/api/cases/{cid}/requirements", json={"items": []}, headers=H)
    client.post(f"/api/cases/{cid}/documents/demo", headers=H)
    c = client.post(f"/api/cases/{cid}/process").json()
    assert c["bidder_name"] == "ABC Engineering Pvt. Ltd."
    udyam = next(d for d in c["documents"] if d["doc_type"] == "udyam_certificate")
    assert "OCR" in udyam["method"]
    assert any(f["value"] == "UDYAM-MH-19-0045821" for f in udyam["fields"])
    assert [m["document"] for m in c["missing_documents"]] == ["OEM authorisation"]

    c = client.post(f"/api/cases/{cid}/verify").json()
    status = {r["key"]: r["status"] for r in c["results"]}
    assert status == {"gst": "VERIFIED", "gst_address": "REVIEW", "pan": "VERIFIED", "udyam": "VERIFIED", "turnover": "REVIEW",
                      "oem": "MISSING", "local_content": "VERIFIED", "validity": "VERIFIED", "debarment": "CLEAR"}
    assert c["score"] == 82 and c["risk"] == "MEDIUM"
    for r in c["results"]:
        if r["key"] != "oem":
            assert r["evidence"], r["key"]
    turnover = next(r for r in c["results"] if r["key"] == "turnover")
    ev = next(e for e in turnover["evidence"] if e["kind"] == "document")
    assert ev["page"] == 12 and ev["bbox"]
    img = client.get(f"/api/documents/{ev['document_id']}/page/12", params={"hl": ",".join(map(str, ev["bbox"]))})
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"

    bad = client.post(f"/api/cases/{cid}/decision", json={"decision": "CLARIFY", "remarks": ""}, headers=H)
    assert bad.status_code == 400
    c = client.post(f"/api/cases/{cid}/decision", json={"decision": "CLARIFY", "remarks": "Submit OEM authorisation and FY 2023-24 financials"}, headers=H).json()
    assert c["decision"] == "CLARIFY"
    assert any(a["action"] == "Officer decision" for a in c["audit"])
    assert c["audit_integrity"]["valid"] and "Special Condition 5.4" in c["communication"]


def test_manual_upload_gives_same_result():
    """Uploading the files by hand (no demo shortcut) must produce the same report."""
    from app.config import DEMO_DIR
    cid = client.post("/api/cases", headers=H).json()["id"]
    t = DEMO_DIR / "Tender_GEM-2026-B-5873214.pdf"
    client.post(f"/api/cases/{cid}/tender", files={"file": (t.name, t.read_bytes(), "application/pdf")}, headers=H)
    files = [("files", (p.name, p.read_bytes())) for p in sorted((DEMO_DIR / "bidder").iterdir())]
    client.post(f"/api/cases/{cid}/documents", files=files, headers=H)
    client.post(f"/api/cases/{cid}/process")
    c = client.post(f"/api/cases/{cid}/verify").json()
    assert c["score"] == 82 and c["risk"] == "MEDIUM"


def test_audit_tamper_detected():
    from app.db import SessionLocal
    from app import models as m
    from app.services.pipeline import verify_chain
    db = SessionLocal()
    case = db.query(m.Case).first()
    assert verify_chain(case)["valid"]
    case.audit[3].result = "tampered"
    assert not verify_chain(case)["valid"]
    db.rollback()
