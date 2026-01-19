from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Document, DocumentVersion

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class DocumentIn(BaseModel):
    title: str = Field(..., min_length=1)
    doc_type: str = Field(..., min_length=1)  # resume | cover_letter | email | notes
    application_id: Optional[int] = None  # reserved for later linkage


class DocumentOut(BaseModel):
    id: int
    title: str
    doc_type: str
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentVersionOut(BaseModel):
    id: int
    document_id: int
    created_at: datetime
    content: str

    class Config:
        from_attributes = True


class GenerateRequest(BaseModel):
    doc_type: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)
    context: Optional[str] = None
    application_id: Optional[int] = None


@router.get("/documents", response_model=List[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    return db.query(Document).order_by(Document.created_at.desc()).all()


@router.post("/documents", response_model=DocumentOut)
def create_document(payload: DocumentIn, db: Session = Depends(get_db)):
    doc = Document(
        title=payload.title,
        doc_type=payload.doc_type,
        created_at=datetime.now(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


@router.get("/documents/{doc_id}/versions", response_model=List[DocumentVersionOut])
def list_versions(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Document not found")

    return (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == doc_id)
        .order_by(DocumentVersion.created_at.desc())
        .all()
    )


@router.post("/documents/generate", response_model=DocumentVersionOut)
def generate_document(req: GenerateRequest, db: Session = Depends(get_db)):
    # Placeholder generation: connect OpenAI next.
    now = datetime.now()

    doc = Document(
        title=f"Generated {req.doc_type} ({now.isoformat(timespec='seconds')}Z)",
        doc_type=req.doc_type,
        created_at=now,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    content = f"""[DRAFT - generated]
Doc type: {req.doc_type}

Prompt:
{req.prompt}

Context:
{req.context or "(none)"}
"""

    ver = DocumentVersion(
        document_id=doc.id,
        created_at=datetime.now(),
        content=content,
    )
    db.add(ver)
    db.commit()
    db.refresh(ver)
    return ver
