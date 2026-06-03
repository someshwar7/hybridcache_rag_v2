"""
core/reranker.py
-----------------
Reranks retrieved candidate chunks using the Cohere Rerank API.

Uses the state-of-the-art `rerank-english-v3.0` model to compute a more accurate 
relevance score between the query and each chunk, re-sorting them to prioritize 
the most contextually matching snippets.
"""

import os
from typing import List, Dict, Any
import cohere
from dotenv import load_dotenv
from logs.logs_router import api_logger

load_dotenv()

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
RERANK_MODEL = "rerank-english-v3.0"

from core.embeddings import get_cohere_client
from sqlalchemy.orm import Session
from typing import Optional


def rerank_results(
    query: str,
    candidates: List[Dict[str, Any]],
    top_k: int = 5,
    session_id: Optional[str] = None,
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """
    Reranks candidate chunks based on semantic relevance to the query.
    Dynamically loads the Cohere client based on active session configuration.
    """
    if not candidates:
        return []

    # Prepare document text list for Cohere rerank API
    documents = [c["chunk_text"] for c in candidates]

    # Limit top_k to number of candidates
    top_k = min(top_k, len(candidates))

    try:
        client = get_cohere_client(session_id, db)
        api_logger.info(f"Initiating Cohere Rerank API Call - Model: {RERANK_MODEL}, Candidates: {len(documents)}")
        response = client.rerank(
            model=RERANK_MODEL,
            query=query,
            documents=documents,
            top_n=top_k
        )
        api_logger.info("Cohere Rerank API Call Success")
        
        reranked_results = []
        for rank, result in enumerate(response.results, start=1):
            idx = result.index
            candidate = candidates[idx].copy()
            # Update score and rank based on rerank response
            candidate["similarity"] = round(float(result.relevance_score), 4)
            candidate["rank"] = rank
            reranked_results.append(candidate)
            
        return reranked_results
    except Exception as e:
        err_msg = str(e)
        if "rate limit" in err_msg.lower() or "429" in err_msg:
            api_logger.warning(f"Cohere Rerank API Rate Limit Hit! Detail: {err_msg}")
        else:
            api_logger.error(f"Error during Cohere Rerank API Call: {err_msg}")
        # Fallback to original candidates if API call fails
        print(f"Error during Cohere Rerank: {e}. Falling back to vector search results.")
        # Retain original ranking but slice to top_k
        fallback_results = []
        for rank, c in enumerate(candidates[:top_k], start=1):
            candidate = c.copy()
            candidate["rank"] = rank
            fallback_results.append(candidate)
        return fallback_results

