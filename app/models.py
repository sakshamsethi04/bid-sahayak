"""Database models. SQLite by default; set DATABASE_URL for PostgreSQL."""
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .db import Base


def now():
    return datetime.now()


class Case(Base):
    """One verification case = one bidder evaluated against one tender."""
    __tablename__ = "cases"
    id = Column(Integer, primary_key=True)
    reference = Column(String, unique=True)
    status = Column(String, default="DRAFT")  # DRAFT, CHECKLIST, DOCUMENTS, EXTRACTED, VERIFIED, DECIDED
    bidder_name = Column(String, default="")
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)
    score = Column(Float, nullable=True)
    risk = Column(String, nullable=True)
    recommendation = Column(Text, nullable=True)
    recommendation_source = Column(String, nullable=True)
    decision = Column(String, nullable=True)  # QUALIFY, CLARIFY, REJECT
    decision_remarks = Column(Text, nullable=True)
    decided_by = Column(String, nullable=True)
    decided_at = Column(DateTime, nullable=True)
    communication = Column(Text, nullable=True)  # clarification / rejection letter drafted on decision

    tender = relationship("Tender", uselist=False, back_populates="case", cascade="all, delete-orphan")
    requirements = relationship("Requirement", back_populates="case", cascade="all, delete-orphan",
                                order_by="Requirement.position")
    documents = relationship("Document", back_populates="case", cascade="all, delete-orphan")
    results = relationship("CheckResult", back_populates="case", cascade="all, delete-orphan",
                           order_by="CheckResult.position")
    audit = relationship("AuditEvent", back_populates="case", cascade="all, delete-orphan",
                         order_by="AuditEvent.ts")


class Tender(Base):
    __tablename__ = "tenders"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    filename = Column(String)
    path = Column(String)
    pages = Column(Integer, default=0)
    meta = Column(JSON, default=dict)  # tender no., buyer, item, dates...
    analysis = Column(JSON, default=list)  # steps shown in "Analyzing tender"
    case = relationship("Case", back_populates="tender")


class Requirement(Base):
    __tablename__ = "requirements"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    position = Column(Integer, default=0)
    key = Column(String)  # gst, pan, udyam, turnover, oem, local_content, validity, debarment
    label = Column(String)
    category = Column(String)  # Statutory, Financial, Technical, Integrity
    mandatory = Column(Boolean, default=True)
    enabled = Column(Boolean, default=True)
    weight = Column(Float, default=10)
    params = Column(JSON, default=dict)
    clause = Column(Text, default="")
    clause_page = Column(Integer, nullable=True)
    case = relationship("Case", back_populates="requirements")


class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    filename = Column(String)
    path = Column(String)
    mime = Column(String)
    doc_type = Column(String, nullable=True)  # gst_certificate, pan_card, ...
    doc_type_label = Column(String, nullable=True)
    pages = Column(Integer, default=0)
    method = Column(String, nullable=True)  # "Text layer" | "OCR (Tesseract)"
    status = Column(String, default="UPLOADED")  # UPLOADED, PROCESSED, FAILED
    processing_ms = Column(Integer, nullable=True)
    page_text = Column(JSON, default=list)
    fields = relationship("ExtractedField", back_populates="document", cascade="all, delete-orphan")
    case = relationship("Case", back_populates="documents")


class ExtractedField(Base):
    __tablename__ = "fields"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"))
    name = Column(String)
    label = Column(String)
    value = Column(String)
    page = Column(Integer)
    snippet = Column(Text)
    confidence = Column(Float)
    bbox = Column(JSON, nullable=True)  # [x0, top, x1, bottom] in page points / pixels
    document = relationship("Document", back_populates="fields")


class CheckResult(Base):
    __tablename__ = "results"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    position = Column(Integer, default=0)
    requirement_key = Column(String)
    label = Column(String)
    category = Column(String)
    status = Column(String)  # VERIFIED, REVIEW, MISSING, FAILED, CLEAR
    severity = Column(String)  # ok, warning, critical
    scored = Column(Boolean, default=True)
    weight = Column(Float, default=0)
    earned = Column(Float, default=0)
    summary = Column(Text)
    expected = Column(Text)
    found = Column(Text)
    reason = Column(Text)
    source = Column(String)  # "Mock GST registry", "Document", ...
    evidence = Column(JSON, default=list)  # [{document_id, filename, page, value, snippet, bbox}]
    case = relationship("Case", back_populates="results")


class AuditEvent(Base):
    __tablename__ = "audit"
    id = Column(Integer, primary_key=True)
    case_id = Column(Integer, ForeignKey("cases.id"))
    ts = Column(DateTime, default=now)
    actor = Column(String)
    action = Column(String)
    result = Column(String)
    detail = Column(Text, default="")
    prev_hash = Column(String, default="")
    hash = Column(String, default="")
    case = relationship("Case", back_populates="audit")
