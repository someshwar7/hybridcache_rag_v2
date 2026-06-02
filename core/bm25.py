"""
core/bm25.py
------------
Full-Text Search (BM25-style) retrieval backed by PostgreSQL ts_rank_cd.

Uses PostgreSQL's built-in tsvector / tsquery to perform keyword-based
ranked retrieval over the embeddings + raw_text + files tables.

Scoring
-------
  ts_rank_cd('{0.1, 0.2, 0.4, 1.0}', weighted_vector, query)
    D=0.1  →  plain body text
    C=0.2  →  (unused)
    B=0.4  →  chunk body   (setweight 'B')
    A=1.0  →  section header (setweight 'A')

  Chunks whose *header* contains the query term score higher (A-weight)
  than chunks where the term only appears in the body (B-weight).

Usage
-----
  from core.bm25 import bm25_search

  results = bm25_search("machine learning", top_k=5)
  results = bm25_search("monuments", top_k=5, document_id=1)
"""

import re
from typing import List, Dict, Any, Optional

from sqlalchemy import text

from core.database import SessionLocal


# ─────────────────────────────────────────────────────────────
# Internal helper
# ─────────────────────────────────────────────────────────────

def _build_ts_query(query: str) -> str:
    """
    Converts a natural-language query string into a PostgreSQL
    tsquery OR expression.

    Example
    -------
      "what is machine learning"  →  "what | is | machine | learning"
    """
    words = re.findall(r"\b\w+\b", query)
    clean = [w.strip() for w in words if w.strip()]
    if not clean:
        raise ValueError(f"Query '{query}' produced no searchable tokens.")
    return " | ".join(clean)


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def bm25_search(
    query: str,
    top_k: int = 5,
    document_id: Optional[int] = None,
    page_no: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve the top-k most relevant chunks for a keyword query
    using PostgreSQL full-text search (ts_rank_cd).

    Parameters
    ----------
    query : str
        Natural language query string from the user.
    top_k : int
        Number of top results to return (default: 5, max: 20).
    document_id : int | None
        If set, restricts search to chunks from this document only.
    page_no : int | None
        If set, restricts search to chunks on this specific page only.

    Returns
    -------
    list[dict]
        Each dict contains:
          - rank           : result rank (1-indexed)
          - bm25_score     : ts_rank_cd score (higher = more relevant)
          - chunk_text     : the raw chunk text
          - page_no        : page number in the source PDF
          - header         : section header (nullable)
          - document_title : original filename of the PDF
          - source_file    : relative path to the source PDF
          - document_id    : ID of the parent document
          - chunk_id       : primary key of the embeddings row
    """

    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    top_k = min(max(1, top_k), 20)
    ts_query = _build_ts_query(query)

    doc_filter = "AND e.document_id = :document_id" if document_id is not None else ""
    page_filter = "AND rt.page_no BETWEEN :page_lo AND :page_hi" if page_no is not None else ""

    SQL = f"""
        SELECT
            e.id                                                         AS chunk_id,
            e.document_id                                                AS document_id,
            e.chunk_text                                                 AS chunk_text,
            rt.page_no                                                   AS page_no,
            rt.header                                                    AS header,
            f.original_filename                                          AS document_title,
            rt.source                                                    AS source_file,
            ts_rank_cd(
                '{{0.1, 0.2, 0.4, 1.0}}',
                setweight(to_tsvector('english', COALESCE(rt.header, '')), 'A') ||
                setweight(to_tsvector('english', e.chunk_text),            'B'),
                to_tsquery('english', :ts_query)
            )                                                            AS bm25_score
        FROM   embeddings  e
        JOIN   raw_text    rt ON rt.content     = e.chunk_text
                             AND rt.document_id = e.document_id
        JOIN   files       f  ON f.id           = e.document_id
        WHERE (
            to_tsvector('english', e.chunk_text)             @@ to_tsquery('english', :ts_query)
            OR
            to_tsvector('english', COALESCE(rt.header, ''))  @@ to_tsquery('english', :ts_query)
        )
        {doc_filter}
        {page_filter}
        ORDER  BY bm25_score DESC
        LIMIT  :top_k
    """

    params: Dict[str, Any] = {
        "ts_query":    ts_query,
        "top_k":       top_k,
    }
    if document_id is not None:
        params["document_id"] = document_id
    if page_no is not None:
        params["page_lo"] = max(1, page_no - 2)
        params["page_hi"] = page_no + 2

    results: List[Dict[str, Any]] = []

    db = SessionLocal()
    try:
        rows = db.execute(text(SQL), params).fetchall()
        for rank, row in enumerate(rows, start=1):
            results.append({
                "rank":           rank,
                "bm25_score":     round(float(row.bm25_score), 4),
                "chunk_text":     row.chunk_text,
                "page_no":        row.page_no,
                "header":         row.header,
                "document_title": row.document_title,
                "source_file":    row.source_file,
                "document_id":    row.document_id,
                "chunk_id":       row.chunk_id,
            })
    finally:
        db.close()

    return results
