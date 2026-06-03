from fastapi import APIRouter, HTTPException
from core.retriever import retrieve_chunks, list_indexed_documents
from data_models import RetrieveRequest, RetrieveResponse, DocumentListResponse
from service.session_manager import update_activity
from logs.logs_router import query_logger

router = APIRouter(prefix="/retriever", tags=["Retriever Search"])

@router.post("/retrieve", response_model=RetrieveResponse)
def retrieve(request: RetrieveRequest):
    """
    Semantic vector search over all indexed PDF chunks.

    Embeds the query using Cohere, then finds the top-k most similar
    chunks in the embeddings table using pgvector cosine distance.
    """
    query_logger.info(f"Processing query: {request.query}")
    if request.session_id:
        update_activity(request.session_id)
    try:
        results = retrieve_chunks(
            query=request.query,
            top_k=request.top_k,
            document_id=request.document_id,
            min_similarity=request.min_similarity,
            use_reranker=request.use_reranker,
            session_id=request.session_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {e}")

    return {
        "success": True,
        "query": request.query,
        "total_results": len(results),
        "results": results,
    }

@router.get("/documents", response_model=DocumentListResponse)
def get_indexed_documents():
    """
    Lists all PDF documents that have been indexed into the vector store.
    Used to populate the document filter dropdown in the UI.
    """
    try:
        docs = list_indexed_documents()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list documents: {e}")

    return {
        "success": True,
        "total": len(docs),
        "documents": docs,
    }
