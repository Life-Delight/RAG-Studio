import logging
import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import CHUNK_SIZE, CHUNK_OVERLAP
from app.models.database import Document, KnowledgeBase, SessionLocal, beijing_now
from app.services.vector_service import VectorService
from app.services.embedding_service import embed_texts
from app.services.bm25_service import rebuild_bm25_index

logger = logging.getLogger(__name__)


def update_doc_progress(
    doc: Document,
    db: Session,
    percent: int,
    message: str,
):
    doc.progress_percent = max(0, min(100, int(percent)))
    doc.progress_message = message
    db.commit()


def split_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Split text into overlapping chunks."""
    if not text.strip():
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break
        start += chunk_size - overlap

    return chunks


def convert_doc_to_docx(file_path: Path) -> Path:
    """Convert legacy .doc file to .docx using LibreOffice headless."""
    output_dir = file_path.parent
    expected_docx = output_dir / f"{file_path.stem}.docx"

    if expected_docx.exists():
        expected_docx.unlink()

    command = [
        "soffice",
        "--headless",
        "--convert-to",
        "docx",
        "--outdir",
        str(output_dir),
        str(file_path),
    ]

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise ValueError(f".doc 转换失败：{stderr or 'LibreOffice conversion failed'}")

    if not expected_docx.exists():
        raise ValueError(".doc 转换失败：未生成 .docx 文件")

    return expected_docx


def extract_text_from_pdf_with_pdfplumber(file_path: Path) -> str:
    import pdfplumber

    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts).strip()


def extract_text_from_pdf_with_ocr(
    file_path: Path,
    on_progress: Optional[Callable[[int, int], None]] = None,
) -> str:
    """OCR fallback for scanned PDFs."""
    try:
        from pdf2image import convert_from_path, pdfinfo_from_path
        import pytesseract
    except Exception as e:
        raise ValueError(f"PDF OCR 依赖不可用：{e}")

    try:
        pdf_info = pdfinfo_from_path(str(file_path))
        total_pages = int(pdf_info.get("Pages", 0))
    except Exception:
        total_pages = 0

    text_parts = []

    if total_pages <= 0:
        try:
            images = convert_from_path(str(file_path), dpi=150)
        except Exception as e:
            raise ValueError(f"PDF 转图片失败：{e}")

        total_pages = len(images)
        for idx, image in enumerate(images, start=1):
            page_text = pytesseract.image_to_string(image, lang="chi_sim+eng")
            if page_text and page_text.strip():
                text_parts.append(page_text.strip())
            if on_progress:
                on_progress(idx, total_pages)
        return "\n".join(text_parts).strip()

    for page_idx in range(1, total_pages + 1):
        try:
            images = convert_from_path(
                str(file_path),
                dpi=150,
                first_page=page_idx,
                last_page=page_idx,
                thread_count=1,
            )
        except Exception as e:
            raise ValueError(f"PDF 第{page_idx}页转图片失败：{e}")

        if not images:
            if on_progress:
                on_progress(page_idx, total_pages)
            continue

        page_text = pytesseract.image_to_string(images[0], lang="chi_sim+eng")
        if page_text and page_text.strip():
            text_parts.append(page_text.strip())

        if on_progress:
            on_progress(page_idx, total_pages)

    return "\n".join(text_parts).strip()


def extract_text_from_file(
    file_path: Path,
    file_type: str,
    on_ocr_progress: Optional[Callable[[int, int], None]] = None,
) -> str:
    """Extract text content from various file formats."""
    try:
        if file_type in [".txt", ".md"]:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

        elif file_type == ".pdf":
            text = extract_text_from_pdf_with_pdfplumber(file_path)
            if text:
                return text

            logger.warning("pdfplumber extracted empty text for %s, trying OCR fallback", file_path.name)
            ocr_text = extract_text_from_pdf_with_ocr(file_path, on_progress=on_ocr_progress)
            if ocr_text:
                logger.info("OCR fallback extracted %s characters from %s", len(ocr_text), file_path.name)
                return ocr_text

            raise ValueError("No text content extracted from file (PDF可能为扫描件，OCR也未识别到文本)")

        elif file_type == ".docx":
            from docx import Document as DocxDocument
            doc = DocxDocument(file_path)
            parts = [para.text.strip() for para in doc.paragraphs if para.text and para.text.strip()]
            return "\n".join(parts)

        elif file_type == ".csv":
            import csv
            rows = []
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f)
                for row in reader:
                    rows.append(", ".join(row))
            return "\n".join(rows)

        else:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
    except Exception as e:
        logger.error(f"Error extracting text from {file_path}: {e}")
        raise


def prepare_extract_target(file_path: Path, file_type: str) -> Tuple[Path, str]:
    """Normalize source file before text extraction."""
    if file_type == ".doc":
        logger.info(f"Converting legacy .doc file: {file_path.name}")
        converted_path = convert_doc_to_docx(file_path)
        return converted_path, ".docx"
    return file_path, file_type


def process_document(doc_id: int, file_path: Path, kb_id: int, db: Session):
    """Process a document: extract text, chunk, embed, store in vector DB."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        logger.error(f"Document {doc_id} not found")
        return

    converted_path: Optional[Path] = None

    try:
        doc.status = "processing"
        doc.progress_percent = 1
        doc.progress_message = "等待处理"
        doc.error_message = ""
        db.commit()

        file_type = Path(doc.original_name).suffix.lower()
        logger.info(f"Processing document: {doc.original_name} (type: {file_type})")

        update_doc_progress(doc, db, 5, "准备解析文档")
        extract_path, extract_type = prepare_extract_target(file_path, file_type)
        if extract_path != file_path:
            converted_path = extract_path

        update_doc_progress(doc, db, 12, "提取文本中")

        def _on_ocr_progress(done: int, total: int):
            if total <= 0:
                return
            percent = 12 + int(done * 48 / total)
            update_doc_progress(doc, db, percent, f"OCR识别中（{done}/{total}页）")

        text = extract_text_from_file(extract_path, extract_type, on_ocr_progress=_on_ocr_progress)
        if not text.strip():
            raise ValueError("No text content extracted from file")

        logger.info(f"Extracted {len(text)} characters from {doc.original_name}")

        update_doc_progress(doc, db, 65, "文本分块中")
        chunks = split_text(text)
        if not chunks:
            raise ValueError("No chunks created from text")

        logger.info(f"Created {len(chunks)} chunks from {doc.original_name}")

        update_doc_progress(doc, db, 75, "向量化中")
        embeddings = embed_texts(chunks)

        update_doc_progress(doc, db, 90, "写入向量库中")
        vector_service = VectorService(kb_id)
        vector_service.add_documents(
            doc_id=doc_id,
            filename=doc.original_name,
            chunks=chunks,
            embeddings=embeddings
        )

        doc.status = "ready"
        doc.chunk_count = len(chunks)
        doc.updated_at = beijing_now()
        doc.error_message = ""
        doc.progress_percent = 100
        doc.progress_message = "处理完成"
        db.commit()

        kb = db.query(KnowledgeBase).filter(KnowledgeBase.id == kb_id).first()
        if kb:
            kb.document_count = db.query(Document).filter(
                Document.kb_id == kb_id,
                Document.status == "ready"
            ).count()
            db.commit()

        rebuild_bm25_index(kb_id)
        logger.info(f"Document {doc.original_name} processed successfully")

    except Exception as e:
        logger.error(f"Error processing document {doc_id}: {e}")
        doc.status = "failed"
        doc.error_message = str(e)
        doc.progress_message = "处理失败"
        db.commit()
        raise
    finally:
        if converted_path and converted_path.exists():
            try:
                converted_path.unlink()
            except Exception as cleanup_error:
                logger.warning(f"Failed to remove temporary converted file {converted_path}: {cleanup_error}")


def process_document_task(doc_id: int, file_path: Path, kb_id: int):
    db = SessionLocal()
    try:
        process_document(doc_id, file_path, kb_id, db)
    except Exception:
        logger.exception("Background document task failed: doc_id=%s", doc_id)
    finally:
        db.close()
