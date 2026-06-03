import os
import json
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from core.database import engine
from core.retriever import list_indexed_documents
from core.intent_classifier import classify_intent
from data_models import RetrieveRequest
from helpers import align_result_attributes
from service.session_manager import update_activity

router = APIRouter(prefix="/retriever", tags=["Retriever Classify"])

@router.post("/classify")
def classify_query(request: RetrieveRequest):
    """
    Classifies the user query using the template-based routing engine,
    applies strict attribute alignment, caps RAG and Web Search results at 3,
    and supports document header extraction logic.
    """
    if request.session_id:
        update_activity(request.session_id)
    try:
        query_lower = request.query.lower()
        
        # 1. Detect if the user is asking specifically to retrieve/list headers
        is_header_query = "header" in query_lower or "headers" in query_lower
        
        doc_id = request.document_id
        doc_title = "Document"
        
        # Auto-detect document ID from the query if not explicitly set
        try:
            docs = list_indexed_documents()
            for doc in docs:
                filename = doc["filename"]
                filename_lower = filename.lower()
                name_without_ext = os.path.splitext(filename_lower)[0]
                if doc_id is None and (filename_lower in query_lower or (len(name_without_ext) > 3 and name_without_ext in query_lower)):
                    doc_id = doc["document_id"]
                    doc_title = filename
                    break
                elif doc_id is not None and doc["document_id"] == doc_id:
                    doc_title = filename
        except Exception:
            pass

        # 2. Custom header extraction branch
        if is_header_query and doc_id is not None:
            sql = """
                SELECT DISTINCT header, page_no, source 
                FROM   raw_text 
                WHERE  document_id = :doc_id 
                       AND header IS NOT NULL 
                       AND header != '' 
                ORDER  BY page_no
            """
            aligned_results = []
            with engine.connect() as conn:
                rows = conn.execute(text(sql), {"doc_id": doc_id}).fetchall()
                for idx, row in enumerate(rows, start=1):
                    clean_header = row.header.lstrip('#').strip()
                    raw_item = {
                        "chunk_text":          f"• {clean_header} (Page {row.page_no})",
                        "page_no":             row.page_no,
                        "header":              row.header,
                        "document_title":      doc_title,
                        "document_id":         doc_id,
                        "source":              row.source,
                        "overall_accuracy":    100.0,
                        "similarity":          1.0000,
                        "rank":                idx,
                        "has_tables":          False,
                        "has_images":          False,
                        "key_takeaways":       [],
                        "suggested_followups": []
                    }
                    aligned_results.append(align_result_attributes(raw_item))
            
            intent = "rag"
            explanation = "query requests document structural headers directly; fetched unique header records from DB"
            
        else:
            # Standard path: Run core intent classification with top_k = 3
            docs = list_indexed_documents()
            has_docs = len(docs) > 0
            classification = classify_intent(request.query, has_documents=has_docs, top_k=3, session_id=request.session_id)
            intent = classification.intent
            explanation = classification.explanation
            
            # Standardize and align all result structures, enforcing limit of 3 for RAG & Web Search
            aligned_results = []
            if classification.results:
                results_to_process = classification.results
                if classification.intent in ["rag", "web_search"]:
                    results_to_process = classification.results[:3]

                for item in results_to_process:
                    aligned_results.append(align_result_attributes(item))

        # Print full standardized metadata to backend console
        print("\n" + "="*80)
        print(f"[BACKEND LOG] User Query: {request.query}")
        print(f"[BACKEND LOG] Intent Classified: {intent.upper()}")
        print(f"[BACKEND LOG] Reason: {explanation}")
        print("[BACKEND LOG] Standardized Aligned Results:")
        print(json.dumps(aligned_results, indent=2))
        print("="*80 + "\n")

        return {
            "status": "success",
            "message": "User intent classified successfully",
            "data": {
                "query": request.query,
                "intent": intent,
                "explanation": explanation,
                "results": aligned_results
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Classification failed: {str(e)}")
