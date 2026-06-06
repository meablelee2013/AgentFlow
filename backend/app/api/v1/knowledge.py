"""Knowledge Base API — document upload and RAG query"""
import uuid
import shutil
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.api.v1.deps import get_db
from app.core.rag.pipeline import RAGPipeline
from app.models.knowledge import KnowledgeBase, Document

logger = structlog.get_logger()
router = APIRouter(prefix="/knowledge", tags=["knowledge"])

UPLOAD_DIR = Path(__file__).resolve().parents[4] / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    status: str


class UrlIngestRequest(BaseModel):
    url: str = Field(..., min_length=1, description="Web page URL to ingest")
    knowledge_base_id: str | None = None


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    knowledge_base_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class QueryResponse(BaseModel):
    answer: str
    chunks: list[dict]


class ChunkResponse(BaseModel):
    content: str
    score: float
    source: str | None


@router.post("/upload", response_model=KnowledgeBaseResponse)
async def upload_document(
    file: UploadFile = File(...),
    knowledge_base_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document for RAG ingestion.

    Supported formats: PDF, DOCX, MD, TXT
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Save uploaded file
    file_path = UPLOAD_DIR / f"{uuid.uuid4()}_{file.filename}"
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Run RAG ingestion pipeline
    pipeline = RAGPipeline(db)
    kb_id = uuid.UUID(knowledge_base_id) if knowledge_base_id else None

    try:
        kb = await pipeline.ingest_file(
            str(file_path), knowledge_base_id=kb_id, original_filename=file.filename
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        # Clean up uploaded file after processing
        file_path.unlink(missing_ok=True)

    return KnowledgeBaseResponse(
        id=str(kb.id),
        name=kb.name,
        status=kb.status,
    )


@router.post("/ingest-url", response_model=KnowledgeBaseResponse)
async def ingest_url(
    req: UrlIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Ingest a web page URL into the RAG pipeline.

    Fetches the page, extracts text content, and indexes it for retrieval.
    """
    pipeline = RAGPipeline(db)
    kb_id = uuid.UUID(req.knowledge_base_id) if req.knowledge_base_id else None

    try:
        kb = await pipeline.ingest_url(req.url, knowledge_base_id=kb_id)
    except Exception as e:
        err_type = type(e).__name__
        err_msg = str(e)

        # Provide user-friendly error for HTTP errors
        if hasattr(e, "response") and hasattr(e.response, "status_code"):
            status = e.response.status_code
            err_msg = (
                f"URL returned HTTP {status}. "
                f"The site may block crawlers — try a URL that allows bot access."
            )

        logger.error("URL ingestion failed", url=req.url, error=f"{err_type}: {err_msg}")
        raise HTTPException(status_code=400, detail=err_msg)

    return KnowledgeBaseResponse(
        id=str(kb.id),
        name=kb.name,
        status=kb.status,
    )


@router.post("/query", response_model=QueryResponse)
async def query_knowledge(
    req: QueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """Query the RAG knowledge base.

    Returns retrieved chunks with scores and citation sources.
    """
    pipeline = RAGPipeline(db)
    kb_id = uuid.UUID(req.knowledge_base_id) if req.knowledge_base_id else None

    result = await pipeline.query(
        question=req.question,
        top_k=req.top_k,
        knowledge_base_id=kb_id,
    )

    return QueryResponse(
        answer="",  # Phase 2: LLM-generated answer
        chunks=[
            {
                "content": c["content"],
                "score": c["score"],
                "source": c.get("metadata", ""),
            }
            for c in result["chunks"]
        ],
    )


class CreateBaseRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


@router.post("/bases", response_model=KnowledgeBaseResponse, status_code=201)
async def create_knowledge_base(
    req: CreateBaseRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new knowledge base."""
    kb = KnowledgeBase(name=req.name, description=req.description, status="ready")
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return KnowledgeBaseResponse(id=str(kb.id), name=kb.name, status=kb.status)


@router.delete("/bases/{kb_id}", status_code=204)
async def delete_knowledge_base(kb_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a knowledge base and all its documents."""
    kb = await db.get(KnowledgeBase, uuid.UUID(kb_id))
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    await db.delete(kb)
    await db.commit()


@router.get("/bases", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(db: AsyncSession = Depends(get_db)):
    """List all knowledge bases."""
    from sqlalchemy import select
    result = await db.execute(select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc()))
    kbs = result.scalars().all()
    return [
        KnowledgeBaseResponse(id=str(kb.id), name=kb.name, status=kb.status)
        for kb in kbs
    ]


class DocumentResponse(BaseModel):
    id: str
    filename: str
    file_type: str
    chunk_count: int
    status: str
    created_at: str


@router.get("/bases/{kb_id}/documents", response_model=list[DocumentResponse])
async def list_documents(kb_id: str, db: AsyncSession = Depends(get_db)):
    """List all documents in a knowledge base."""
    from sqlalchemy import select
    result = await db.execute(
        select(Document).where(Document.knowledge_base_id == uuid.UUID(kb_id))
        .order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()
    return [
        DocumentResponse(
            id=str(d.id),
            filename=d.filename,
            file_type=d.file_type,
            chunk_count=d.chunk_count,
            status=d.status,
            created_at=d.created_at.isoformat() if d.created_at else "",
        )
        for d in docs
    ]


@router.delete("/bases/{kb_id}/documents/{doc_id}", status_code=204)
async def delete_document(kb_id: str, doc_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a document and all its chunks (vectors) from the knowledge base."""
    doc = await db.get(Document, uuid.UUID(doc_id))
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # Cascading delete removes associated document_chunks (vectors)
    await db.delete(doc)
    await db.commit()
