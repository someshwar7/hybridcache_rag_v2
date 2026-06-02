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

COHERE_API_KEY = os.getenv("COHERE_API_KEY")
RERANK_MODEL = "rerank-english-v3.0"

if not COHERE_API_KEY:
    raise EnvironmentError("COHERE_API_KEY not found in environment.")

_client = cohere.Client(api_key=COHERE_API_KEY)


def rerank_results(
    query: str,
    candidates: List[Dict[str, Any]],
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Reranks candidate chunks based on semantic relevance to the query.

    Parameters
    ----------
    query : str
        The user's search query.
    candidates : list[dict]
        List of dictionary objects returned from the initial vector search.
        Each dictionary must contain at least `chunk_text`.
    top_k : int
        The number of top results to return after reranking.

    Returns
    -------
    list[dict]
        The reranked and filtered results. Each dictionary will have:
          - similarity: updated to the rerank relevance score (0.0 - 1.0)
          - rank: updated to the new rank (1-indexed)
          - other metadata preserved
    """
    if not candidates:
        return []

    # Prepare document text list for Cohere rerank API
    documents = [c["chunk_text"] for c in candidates]

    # Limit top_k to number of candidates
    top_k = min(top_k, len(candidates))

    try:
        api_logger.info(f"Initiating Cohere Rerank API Call - Model: {RERANK_MODEL}, Candidates: {len(documents)}")
        response = _client.rerank(
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
