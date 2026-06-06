"""Knowledge Base API — document upload and RAG query"""
import uuid
import shutil
from pathlib import Path

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
        kb = await pipeline.ingest_file(str(file_path), knowledge_base_id=kb_id)
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
        logger.error("URL ingestion failed", url=req.url, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))

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
