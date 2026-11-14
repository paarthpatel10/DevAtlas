"""
FastAPI Application — main API entry point for the Analytics Copilot.
"""

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import os
from app.config.settings import settings
from app.memory.dynamodb_memory import DynamoDBMemory
from app.memory.inmemory_memory import InMemoryConversationMemory
from app.models.schemas import (
    AskRequest,
    AskResponse,
    HistoryResponse,
    Source,
)
from app.observability.langsmith_client import configure_langsmith
from app.rag.chunker import RecursiveChunker
from app.rag.embedder import BedrockEmbedder
from app.rag.generator import LLMGenerator
from app.rag.opensearch_client import OpenSearchClient
from app.rag.retriever import ContextBuilder, HybridRetriever
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# ── Configure LangSmith tracing at startup ────────────────────────────────────
configure_langsmith()

# ── FastAPI Application ───────────────────────────────────────────────────────
app = FastAPI(
    title="Analytics Copilot API",
    description="Enterprise RAG Copilot",
    version="3.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Upload size limit
MAX_UPLOAD_SIZE_MB = settings.MAX_UPLOAD_SIZE_MB
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# ── Initialize Services ──────────────────────────────────────────────────────
chunker = RecursiveChunker()
embedder = BedrockEmbedder()
os_client = OpenSearchClient()
retriever = HybridRetriever()
llm_gen = LLMGenerator()
USE_DYNAMODB = os.getenv("USE_DYNAMODB", "false").lower() == "true"

if USE_DYNAMODB:
    try:
        memory = DynamoDBMemory()
        logger.info("Conversation memory: DynamoDB")
    except Exception as e:
        logger.warning(f"DynamoDB unavailable ({e}), falling back to in-memory storage")
        memory = InMemoryConversationMemory()
else:
    memory = InMemoryConversationMemory()


# ══════════════════════════════════════════════════════════════════════════════
# MILESTONE 2 ENDPOINTS (Preserved)
# ══════════════════════════════════════════════════════════════════════════════


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Uploads and processes a PDF document into the RAG pipeline."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    try:
        content = await file.read()

        if len(content) > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_SIZE_MB}MB.",
            )

        # 0. Upload to S3
        import boto3
        try:
            s3_client = boto3.client("s3", region_name=settings.AWS_REGION)
            s3_client.put_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=f"uploads/{file.filename}",
                Body=content,
                ContentType="application/pdf"
            )
            logger.info(f"Successfully uploaded {file.filename} to S3 bucket {settings.S3_BUCKET_NAME}")
        except Exception as s3_error:
            logger.error(f"Failed to upload to S3: {s3_error}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload document to S3."
            )

        # Import PDF extractor here to avoid heavyweight import at module level
        from app.rag.chunker import RecursiveChunker

        # 1. Extract text
        from pypdf import PdfReader
        import io

        pdf_document = PdfReader(io.BytesIO(content))
        pages = []
        for page_num in range(len(pdf_document.pages)):
            page = pdf_document.pages[page_num]
            text = page.extract_text()
            if text and text.strip():
                pages.append({
                    "text": text,
                    "metadata": {
                        "source": file.filename,
                        "page_number": page_num + 1,
                        "total_pages": len(pdf_document.pages),
                    },
                })

        # 2. Chunking
        chunks = chunker.chunk_documents(pages)

        # 3. Embedding
        texts = [chunk["text"] for chunk in chunks]
        embeddings = embedder.generate_embeddings(texts)

        # 4. Indexing
        os_client.index_chunks(chunks, embeddings)

        return {
            "message": "File processed and indexed successfully",
            "chunks": len(chunks),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing upload: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while processing the document.",
        )


@app.post("/ask", response_model=AskResponse)
async def ask_question(request: AskRequest):
    """Milestone 2 RAG endpoint — preserved for backward compatibility."""
    try:
        # 1. Retrieve Chat History
        history = memory.get_history(request.session_id, limit=5)

        # 2. Hybrid Retrieval + Context Building
        result = retriever.retrieve_and_build_context(request.query, top_k=5)
        context = result["context"]
        sources = result["sources"]

        # 3. LLM Generation
        answer = llm_gen.generate_response(request.query, context, history)

        # If the LLM didn't use the sources, don't return them
        if "[Source" not in answer:
            sources = []

        # 4. Save Memory
        memory.add_message(request.session_id, "user", request.query)
        memory.add_message(request.session_id, "assistant", answer)

        return AskResponse(answer=answer, sources=sources)

    except Exception as e:
        logger.error(f"Error processing question: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while generating a response.",
        )


@app.get("/history/{session_id}", response_model=HistoryResponse)
async def get_history(session_id: str):
    """Retrieves conversation history for a session."""
    try:
        history = memory.get_history(session_id)
        return HistoryResponse(history=history)
    except Exception as e:
        logger.error(f"Error fetching history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while fetching chat history.",
        )


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)
