"""
core/hybrid_retriever.py
------------------------
Hybrid retriever that blends BM25 (keyword) and Vector (semantic) results,
normalises their scores, blends them using a weighted alpha parameter,
and reranks the final candidates using Cohere Rerank.
"""

from typing import List, Dict, Any, Optional
from core.retriever import retrieve_chunks
from core.bm25 import bm25_search
from core.database import SessionLocal
from core.reranker import rerank_results
from schemas.table_schema import TableData
from schemas.image_schema import Image
from sqlalchemy.orm import Session


def minmax(values: List[float]) -> List[float]:
    """
    Scale values into the range [0.0, 1.0].
    """
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi == lo:
        return [1.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]


def retrieve_hybrid_chunks(
    query: str,
    top_k: int = 5,
    alpha: float = 0.5,
    pool_size: int = 20,
    document_id: Optional[int] = None,
    page_no: Optional[int] = None,
    session_id: Optional[str] = None,
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:

    """
    Retrieve the top-k most relevant chunks using a hybrid approach:
    1. BM25 Search
    2. Vector Similarity Search
    3. Min-Max Normalisation of scores
    4. Alpha-weighted blend
    5. Cohere Rerank pipeline
    6. Page context checks (tables/images presence)

    Parameters
    ----------
    query : str
        The user's query.
    top_k : int
        Number of top results to return.
    alpha : float
        Weighted blend parameter: 0.0 = pure BM25, 1.0 = pure Vector.
    pool_size : int
        Size of candidate pool to retrieve from each retriever.
    document_id : int | None
        Optional document ID to restrict the search.
    page_no : int | None
        Optional page number to restrict the search.

    Returns
    -------
    list[dict]
        List of reranked candidate dictionaries with updated metadata.
    """
    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    # ── Redis Cache Check ──
    from service.session_manager import redis_client
    import json

    metadata = {
        "query": query.strip(),
        "top_k": top_k,
        "alpha": alpha,
        "pool_size": pool_size,
        "document_id": document_id,
        "page_no": page_no
    }
    cache_key = f"cache:hybrid:{json.dumps(metadata, sort_keys=True)}"

    if redis_client:
        try:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                print(f"[Redis Cache] Hit for hybrid: {cache_key}")
                return json.loads(cached_data)
        except Exception as e:
            print(f"[Redis Cache Error] Read failed: {e}")

    # 1. Fetch keyword search results
    bm25_results = bm25_search(
        query, 
        top_k=pool_size, 
        document_id=document_id, 
        page_no=page_no
    )

    # 2. Fetch vector search results (skip reranker in initial vector fetch)
    vector_results = retrieve_chunks(
        query, 
        top_k=pool_size, 
        document_id=document_id, 
        use_reranker=False,
        page_no=page_no,
        session_id=session_id,
        db=db
    )

    # 3. Align results into a unique set
    bm25_map = {(r["document_id"], r["chunk_text"]): r for r in bm25_results}
    vec_map = {
        (r["document_id"], r["chunk_text"]): r 
        for r in vector_results 
        if r.get("vector_similarity", 0.0) > 0.0
    }

    all_keys = set(bm25_map.keys()) | set(vec_map.keys())
    if not all_keys:
        return []

    keys_list = list(all_keys)
    bm25_raw = [bm25_map[k]["bm25_score"] if k in bm25_map else 0.0 for k in keys_list]
    vec_raw = [vec_map[k]["vector_similarity"] if k in vec_map else 0.0 for k in keys_list]

    # 4. Normalise scores
    bm25_norm = minmax(bm25_raw)
    vec_norm = minmax(vec_raw)

    # 5. Blend scores
    combined = []
    for key, b_n, v_n, b_r, v_r in zip(keys_list, bm25_norm, vec_norm, bm25_raw, vec_raw):
        meta = bm25_map.get(key) or vec_map.get(key)
        score = (alpha * v_n) + ((1 - alpha) * b_n)
        
        combined.append({
            "chunk_text":     meta["chunk_text"],
            "page_no":        meta["page_no"],
            "header":         meta["header"],
            "document_title": meta.get("document_title") or meta.get("filename"),
            "filename":       meta.get("filename") or meta.get("document_title"),
            "document_id":    meta.get("document_id"),
            "source":         meta.get("source") or meta.get("source_file"),
            "bm25_raw":       round(b_r, 4),
            "vector_raw":     round(v_r, 4),
            "bm25_norm":      round(b_n * 100, 2),
            "vector_norm":    round(v_n * 100, 2),
            "score_pct":      round(score * 100, 2),
        })

    # Sort and take candidates to rerank
    combined.sort(key=lambda x: x["score_pct"], reverse=True)
    candidates = combined[:pool_size]

    # 6. Rerank via Cohere
    reranked_results = rerank_results(query, candidates, top_k=top_k, session_id=session_id, db=db)

    # 7. Check presence of tables and images on final results' pages
    opened_db = False
    db_session = db
    if db_session is None:
        db_session = SessionLocal()
        opened_db = True
        
    try:
        for r in reranked_results:
            doc_id = r["document_id"]
            page_no = r["page_no"]
            
            has_table = db_session.query(TableData).filter(
                TableData.document_id == doc_id,
                TableData.page_no == page_no
            ).first() is not None
            
            has_image = db_session.query(Image).filter(
                Image.document_id == doc_id,
                Image.page_no == page_no
            ).first() is not None
            
            r["has_tables"] = has_table
            r["has_images"] = has_image
    finally:
        if opened_db:
            db_session.close()


    if redis_client:
        try:
            redis_client.setex(cache_key, 3600, json.dumps(reranked_results))
            print(f"[Redis Cache] Stored hybrid results for key: {cache_key}")
        except Exception as e:
            print(f"[Redis Cache Error] Write failed: {e}")

    return reranked_results
