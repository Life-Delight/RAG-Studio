import os
import shutil
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.database import get_db, KnowledgeBase, Document, ChatSession, ChatMessage, beijing_now
from app.services.document_service import process_document_task
from app.services.vector_service import VectorService
from app.services.bm25_service import invalidate_bm25_cache
from app.core.config import UPLOAD_DIR

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/knowledge-bases", tags=["knowledge-bases"])


class KBCreate(BaseModel):
    name: str
    description: Optional[str] = ""


class KBUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class KBResponse(BaseModel):
    id: int
    name: str
    description: str
    document_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocResponse(BaseModel):
    id: int
    kb_id: int
    filename: str
    original_name: str
    file_size: int
    file_type: str
    status: str
    chunk_count: int
    progress_percent: int
    progress_message: str
    created_at: datetime
    error_message: str

    class Config:
        from_attributes = True


@router.get("", response_model=List[KBResponse])
def list_knowledge_bases(db: Session = Depends(get_db)):
    return db.query(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()).all()


@router.post("", response_model=KBResponse)
def create_knowledge_base(kb: KBCreate, db: Session = Depends(get_db)):
    new_kb = KnowledgeBase(name=kb.name, description=kb.description or "")
    db.add(new_kb)
    db.commit()
    db.refresh(new_kb)
    return new_kb


@router.get("/{kb_id}", response_model=KBResponse)
def get_knowledge_base(kb_id: int, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


@router.put("/{kb_id}", response_model=KBResponse)
def update_knowledge_base(kb_id: int, data: KBUpdate, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if data.name is not None:
        kb.name = data.name
    if data.description is not None:
        kb.description = data.description
    kb.updated_at = beijing_now()
    db.commit()
    db.refresh(kb)
    return kb


@router.delete("/{kb_id}")
def delete_knowledge_base(kb_id: int, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    docs = db.query(Document).filter(Document.kb_id == kb_id).all()
    for doc in docs:
        fp = UPLOAD_DIR / doc.filename
        if fp.exists():
            fp.unlink()
    db.query(Document).filter(Document.kb_id == kb_id).delete()
    session_ids = [session_id for (session_id,) in db.query(ChatSession.id).filter(ChatSession.kb_id == kb_id).all()]
    if session_ids:
        db.query(ChatMessage).filter(ChatMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
    db.query(ChatSession).filter(ChatSession.kb_id == kb_id).delete(synchronize_session=False)
    vs = VectorService(kb_id)
    vs.delete_collection()
    invalidate_bm25_cache(kb_id)
    db.delete(kb)
    db.commit()
    return {"message": "Knowledge base deleted"}


@router.get("/{kb_id}/documents", response_model=List[DocResponse])
def list_documents(kb_id: int, db: Session = Depends(get_db)):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return db.query(Document).filter(Document.kb_id == kb_id).order_by(Document.created_at.desc()).all()


def _validate_upload_file(file: UploadFile):
    allowed = {".txt", ".pdf", ".docx", ".doc", ".md", ".csv"}
    suffix = Path(file.filename or "file").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(status_code=400, detail=f"File type {suffix} not supported")
    return suffix


async def _save_upload_and_create_doc(
    kb_id: int,
    file: UploadFile,
    db: Session,
    background_tasks: BackgroundTasks,
):
    suffix = _validate_upload_file(file)
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    saved_name = f"{kb_id}_{ts}{suffix}"
    save_path = UPLOAD_DIR / saved_name

    with open(save_path, "wb") as f_out:
        content = await file.read()
        f_out.write(content)

    doc = Document(
        kb_id=kb_id,
        filename=saved_name,
        original_name=file.filename or saved_name,
        file_size=len(content),
        file_type=suffix,
        status="processing",
        progress_percent=1,
        progress_message="已上传，等待处理",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(process_document_task, doc.id, save_path, kb_id)
    return doc


@router.post("/{kb_id}/documents")
async def upload_document(
    kb_id: int,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    doc = await _save_upload_and_create_doc(kb_id, file, db, background_tasks)
    return {"id": doc.id, "original_name": doc.original_name, "status": "processing", "progress_percent": 1}


@router.post("/{kb_id}/documents/batch")
async def upload_documents_batch(
    kb_id: int,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db)
):
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    results: List[Dict[str, Any]] = []
    success_count = 0

    for file in files:
        try:
            doc = await _save_upload_and_create_doc(kb_id, file, db, background_tasks)
            success_count += 1
            results.append({
                "filename": file.filename or "",
                "ok": True,
                "id": doc.id,
                "status": "processing"
            })
        except HTTPException as e:
            results.append({
                "filename": file.filename or "",
                "ok": False,
                "error": e.detail
            })
        except Exception:
            logger.exception("Batch upload failed for file: %s", file.filename)
            results.append({
                "filename": file.filename or "",
                "ok": False,
                "error": "Upload failed"
            })

    return {
        "total": len(files),
        "success": success_count,
        "failed": len(files) - success_count,
        "results": results,
    }


@router.delete("/{kb_id}/documents/{doc_id}")
def delete_document(kb_id: int, doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id, Document.kb_id == kb_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    fp = UPLOAD_DIR / doc.filename
    if fp.exists():
        fp.unlink()
    vs = VectorService(kb_id)
    vs.delete_document(doc_id)
    db.delete(doc)
    db.commit()
    kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
    if kb:
        kb.document_count = db.query(Document).filter(
            Document.kb_id == kb_id,
            Document.status == "ready"
        ).count()
        db.commit()
    return {"message": "Document deleted"}
