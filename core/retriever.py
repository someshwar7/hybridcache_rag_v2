"""
core/retriever.py
-----------------
Vector similarity retriever backed by PostgreSQL + pgvector.

Embeds a user query using Cohere (search_query mode), then performs
a cosine similarity search against the embeddings table to return
the most relevant document chunks and/or tables.

Usage:
    from core.retriever import retrieve_chunks, retrieve_tables

    # text chunks only (default)
    results = retrieve_chunks(query="what is machine learning", top_k=5)

    # include table results alongside chunks
    results = retrieve_chunks(query="show table on page 107", top_k=5, include_tables=True)

    # tables only
    tables  = retrieve_tables(query="revenue table", top_k=3)
"""

from typing import List, Optional, Dict, Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.database import engine
from core.embeddings import get_single_embedding
from core.reranker import rerank_results



# ─────────────────────────────────────────────────────────────
# Main retrieval function
# ─────────────────────────────────────────────────────────────

def retrieve_chunks(
    query: str,
    top_k: int = 5,
    document_id: Optional[int] = None,
    min_similarity: float = 0.0,
    use_reranker: bool = True,
    page_no: Optional[int] = None,
    session_id: Optional[str] = None,
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:

    """
    Retrieve the top-k most relevant chunks for a given query.

    Strategy
    --------
    1. Embed the query using Cohere with input_type='search_query'.
    2. Run a pgvector cosine similarity search on the embeddings table.
    3. Optionally filter by document_id (search within a specific PDF).
    4. Optionally filter by minimum cosine similarity score.
    5. Join with raw_text and files tables to return rich metadata.
    6. Re-rank retrieved candidates using Cohere Reranker.
    7. If include_tables=True, also run retrieve_tables() and append results.

    Parameters
    ----------
    query : str
        Natural language query string from the user.
    top_k : int
        Number of top results to return (default: 5, max: 20).
    document_id : int | None
        If set, restricts search to chunks from this PDF document only.
    min_similarity : float
        Minimum cosine similarity threshold (0.0 – 1.0). Results below
        this score are excluded.
    use_reranker : bool
        If True, retrieves more candidate chunks from pgvector and re-ranks
        them using Cohere Rerank API.
    include_tables : bool
        If True, also retrieves matching tables from the `tables` table and
        appends them (result_type='table') to the returned list.
    page_no : int | None
        If set, restricts search to chunks on this specific page only.

    Returns
    -------
    list[dict]
        Each dict contains:
          - rank          : result rank (1-indexed)
          - result_type   : 'chunk' or 'table'
          - similarity    : relevance score (0–1)
          - chunk_text    : the raw chunk text  (chunks only)
          - header        : section header (nullable)
          - page_no       : page number in the source PDF
          - source        : relative path to the source PDF
          - document_id   : ID of the parent document
          - filename      : original filename of the PDF
          - table_path    : filesystem path to the table file (tables only)
    """

    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    top_k = min(max(1, top_k), 20)

    # ── Step 1: Auto-detect document filter from query if not explicitly set ──
    if document_id is None:
        import os
        try:
            docs = list_indexed_documents()
            query_lower = query.lower()
            for doc in docs:
                filename = doc["filename"]
                filename_lower = filename.lower()
                name_without_ext = os.path.splitext(filename_lower)[0]
                
                # Check if full filename or filename without extension is mentioned in query
                if filename_lower in query_lower or (len(name_without_ext) > 3 and name_without_ext in query_lower):
                    document_id = doc["document_id"]
                    print(f"[Retriever] Auto-detected document ID {document_id} from query for: {filename}")
                    break
        except Exception as e:
            print(f"[Retriever] Warning: Document auto-detection failed: {e}")

    # ── Redis Cache Check ──
    from service.session_manager import redis_client
    import json

    metadata = {
        "query": query.strip(),
        "top_k": top_k,
        "document_id": document_id,
        "min_similarity": min_similarity,
        "use_reranker": use_reranker,
        "page_no": page_no
    }
    cache_key = f"cache:chunks:{json.dumps(metadata, sort_keys=True)}"

    if redis_client:
        try:
            cached_data = redis_client.get(cache_key)
            if cached_data:
                print(f"[Redis Cache] Hit for chunks: {cache_key}")
                return json.loads(cached_data)
        except Exception as e:
            print(f"[Redis Cache Error] Read failed: {e}")

    # If reranking is enabled, retrieve a larger pool of candidate chunks from DB
    db_limit = max(50, top_k * 3) if use_reranker else top_k

    # ── Step 2: Vector Similarity Search (pgvector) ───────────
    query_vector = get_single_embedding(query.strip(), input_type="search_query", session_id=session_id, db=db)
    vector_str   = "[" + ",".join(str(round(v, 8)) for v in query_vector) + "]"
    doc_filter = "AND e.document_id = :doc_id" if document_id is not None else ""
    page_filter = "AND rt.page_no BETWEEN :page_lo AND :page_hi" if page_no is not None else ""

    vec_sql = f"""
        SELECT
            e.id                                                          AS embedding_id,
            e.document_id                                                 AS document_id,
            e.chunk_text                                                  AS chunk_text,
            rt.header                                                     AS header,
            rt.page_no                                                    AS page_no,
            rt.source                                                     AS source,
            f.original_filename                                           AS filename,
            GREATEST(
                1 - (e.content_embedding <=> :vec ::vector),
                COALESCE(1 - (e.header_embedding <=> :vec ::vector), 0)
            )                                                             AS similarity
        FROM   embeddings e
        JOIN   raw_text   rt ON rt.document_id = e.document_id
                             AND rt.content     = e.chunk_text
        JOIN   files      f  ON f.id = e.document_id
        WHERE  1=1
               {doc_filter}
               {page_filter}
               AND GREATEST(
                   1 - (e.content_embedding <=> :vec ::vector),
                   COALESCE(1 - (e.header_embedding <=> :vec ::vector), 0)
                ) >= :min_sim
        ORDER  BY similarity DESC
        LIMIT  :db_limit
    """

    params: Dict[str, Any] = {
        "vec":      vector_str,
        "db_limit": db_limit,
        "min_sim":  min_similarity,
    }
    if document_id is not None:
        params["doc_id"] = document_id
    if page_no is not None:
        params["page_lo"] = max(1, page_no - 2)
        params["page_hi"] = page_no + 2

    vector_results = []
    with engine.connect() as conn:
        rows = conn.execute(text(vec_sql), params).fetchall()
        for idx, row in enumerate(rows, start=1):
            vector_results.append({
                "rank":              idx,
                "similarity":        round(float(row.similarity), 4),
                "chunk_text":        row.chunk_text,
                "header":            row.header,
                "page_no":           row.page_no,
                "source":            row.source,
                "document_id":       row.document_id,
                "filename":          row.filename,
                "vector_similarity": round(float(row.similarity), 4),
                "fts_similarity":    0.0,
            })

    # ── Step 3: Full-Text Keyword Search (PostgreSQL FTS) ───────
    import re
    words = re.findall(r"\b\w+\b", query)
    clean_words = [w.strip() for w in words if w.strip()]
    fts_results = []

    if clean_words:
        fts_query_str = " | ".join(clean_words)
        fts_sql = f"""
            SELECT
                e.id                                                          AS embedding_id,
                e.document_id                                                 AS document_id,
                e.chunk_text                                                  AS chunk_text,
                rt.header                                                     AS header,
                rt.page_no                                                    AS page_no,
                rt.source                                                     AS source,
                f.original_filename                                           AS filename,
                ts_rank_cd(
                    to_tsvector('english', e.chunk_text || ' ' || COALESCE(rt.header, '')),
                    to_tsquery('english', :fts_query)
                )                                                             AS similarity
            FROM   embeddings e
            JOIN   raw_text   rt ON rt.document_id = e.document_id
                                 AND rt.content     = e.chunk_text
            JOIN   files      f  ON f.id = e.document_id
            WHERE  1=1
                   {doc_filter}
                   {page_filter}
                   AND to_tsvector('english', e.chunk_text || ' ' || COALESCE(rt.header, '')) @@ to_tsquery('english', :fts_query)
            ORDER  BY similarity DESC
            LIMIT  :db_limit
        """
        fts_params = {
            "fts_query": fts_query_str,
            "db_limit":  db_limit,
        }
        if document_id is not None:
            fts_params["doc_id"] = document_id
        if page_no is not None:
            fts_params["page_lo"] = max(1, page_no - 2)
            fts_params["page_hi"] = page_no + 2

        try:
            with engine.connect() as conn:
                rows = conn.execute(text(fts_sql), fts_params).fetchall()
                for idx, row in enumerate(rows, start=1):
                    fts_results.append({
                        "rank":              idx,
                        "similarity":        round(float(row.similarity), 4),
                        "chunk_text":        row.chunk_text,
                        "header":            row.header,
                        "page_no":           row.page_no,
                        "source":            row.source,
                        "document_id":       row.document_id,
                        "filename":          row.filename,
                        "vector_similarity": 0.0,
                        "fts_similarity":    round(float(row.similarity), 4),
                    })
        except Exception as e:
            # Resilient fallback: print warning and continue with empty FTS
            print(f"[Retriever] FTS search failed: {e}. Bypassing FTS.")

    # ── Step 4: Combine via Reciprocal Rank Fusion (RRF) ───────
    k = 60
    rrf_scores = {}

    for item in vector_results:
        key = (item["document_id"], item["chunk_text"])
        if key not in rrf_scores:
            rrf_scores[key] = {"score": 0.0, "item": item.copy()}
        rrf_scores[key]["score"] += 1.0 / (k + item["rank"])
        rrf_scores[key]["item"]["vector_similarity"] = item["vector_similarity"]

    for item in fts_results:
        key = (item["document_id"], item["chunk_text"])
        if key not in rrf_scores:
            rrf_scores[key] = {"score": 0.0, "item": item.copy()}
        rrf_scores[key]["score"] += 1.0 / (k + item["rank"])
        rrf_scores[key]["item"]["fts_similarity"] = item["fts_similarity"]

    sorted_entries = sorted(rrf_scores.values(), key=lambda x: x["score"], reverse=True)

    results = []
    for rank, entry in enumerate(sorted_entries, start=1):
        item = entry["item"].copy()
        item["rank"] = rank
        item["similarity"] = round(entry["score"], 6)
        item["rrf_score"] = round(entry["score"], 6)
        
        # Default safety fallbacks
        if "vector_similarity" not in item:
            item["vector_similarity"] = 0.0
        if "fts_similarity" not in item:
            item["fts_similarity"] = 0.0
            
        results.append(item)

    # ── Step 5: Re-rank results if requested ─────────────────
    if use_reranker and results:
        results = rerank_results(query=query, candidates=results, top_k=top_k, session_id=session_id, db=db)

    # Tag every result as 'chunk'
    for r in results:
        r["result_type"] = "chunk"

    # ── Step 6: has_tables + has_images flags — single batch check each ──
    if results:
        # Default both flags to False so keys always exist
        for r in results:
            r["has_tables"] = False
            r["has_images"] = False

        pairs = list({(r["document_id"], r["page_no"]) for r in results
                      if r.get("document_id") and r.get("page_no")})

        if pairs:
            placeholders = ",".join(
                f"(:doc_{i}, :page_{i})" for i in range(len(pairs))
            )
            check_params: Dict[str, Any] = {}
            for i, (doc_id, page_no) in enumerate(pairs):
                check_params[f"doc_{i}"]  = doc_id
                check_params[f"page_{i}"] = page_no

            # ─ tables check ───────────────────────────────────────────
            try:
                tbl_sql = f"""
                    SELECT DISTINCT document_id, page_no
                    FROM   "tables"
                    WHERE  (document_id, page_no) IN ({placeholders})
                """
                with engine.connect() as conn:
                    rows = conn.execute(text(tbl_sql), check_params).fetchall()
                    pages_with_tables = {(row.document_id, row.page_no) for row in rows}
                for r in results:
                    r["has_tables"] = (r.get("document_id"), r.get("page_no")) in pages_with_tables
            except Exception as e:
                print(f"[Retriever] has_tables check failed: {e}")

            # ─ images check ───────────────────────────────────────────
            try:
                img_sql = f"""
                    SELECT DISTINCT document_id, page_no
                    FROM   images
                    WHERE  (document_id, page_no) IN ({placeholders})
                """
                with engine.connect() as conn:
                    rows = conn.execute(text(img_sql), check_params).fetchall()
                    pages_with_images = {(row.document_id, row.page_no) for row in rows}
                for r in results:
                    r["has_images"] = (r.get("document_id"), r.get("page_no")) in pages_with_images
            except Exception as e:
                print(f"[Retriever] has_images check failed: {e}")

    if redis_client:
        try:
            redis_client.setex(cache_key, 3600, json.dumps(results))
            print(f"[Redis Cache] Stored chunks for key: {cache_key}")
        except Exception as e:
            print(f"[Redis Cache Error] Write failed: {e}")

    return results


# ─────────────────────────────────────────────────────────────
# Helper: list all indexed documents
# ─────────────────────────────────────────────────────────────

def list_indexed_documents() -> List[Dict[str, Any]]:
    """
    Returns a list of all documents that have embeddings in the DB.
    Used to populate the document filter dropdown in the UI.
    """
    sql = """
        SELECT
            f.id                AS document_id,
            f.original_filename AS filename,
            f.file_format       AS format,
            f.created_at        AS indexed_at,
            f.session_id        AS session_id,
            COUNT(e.id)         AS chunk_count
        FROM   files      f
        JOIN   embeddings e ON e.document_id = f.id
        GROUP  BY f.id, f.original_filename, f.file_format, f.created_at, f.session_id
        ORDER  BY f.created_at DESC
    """
    with engine.connect() as conn:
        rows = conn.execute(text(sql)).fetchall()

    return [
        {
            "document_id": row.document_id,
            "filename":    row.filename,
            "format":      row.format,
            "indexed_at":  str(row.indexed_at),
            "session_id":  row.session_id,
            "chunk_count": row.chunk_count,
        }
        for row in rows
    ]


# ─────────────────────────────────────────────────────────────
# Table retrieval function
# ─────────────────────────────────────────────────────────────

def retrieve_tables(
    query: str,
    top_k: int = 5,
    document_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve matching tables from the `tables` table and return their paths.

    Strategy
    --------
    1. Query the `tables` table directly.
    2. Filter by document_id if provided.
    3. Match rows whose header text contains any word from the query
       (case-insensitive ILIKE search).
    4. Return table_path, page_no, header, source, document_id.

    Parameters
    ----------
    query : str
        Natural language query — used to match against the header column.
    top_k : int
        Maximum number of table results to return (default: 5).
    document_id : int | None
        If set, restricts search to a specific document only.

    Returns
    -------
    list[dict]
        Each dict contains:
          - rank        : result rank (1-indexed)
          - result_type : always 'table'
          - table_path  : filesystem path to the extracted table file
          - page_no     : page number where the table appears
          - header      : section header of the table
          - source      : source PDF path
          - document_id : parent document ID
          - table_id    : primary key of the tables row
    """

    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    top_k = min(max(1, top_k), 20)

    doc_filter = "AND document_id = :doc_id" if document_id is not None else ""

    # Build ILIKE pattern from the first meaningful word in the query
    import re
    words = [w for w in re.findall(r"\b\w{3,}\b", query.lower())]
    header_filter = ""
    ilike_pattern = None
    if words:
        ilike_pattern = f"%{words[0]}%"
        header_filter = "AND header ILIKE :pattern"

    sql = f"""
        SELECT
            id          AS table_id,
            document_id AS document_id,
            source      AS source,
            header      AS header,
            page_no     AS page_no,
            table_path  AS table_path
        FROM   "tables"
        WHERE  1=1
               {doc_filter}
               {header_filter}
        ORDER  BY page_no ASC
        LIMIT  :top_k
    """

    params: Dict[str, Any] = {"top_k": top_k}
    if document_id is not None:
        params["doc_id"] = document_id
    if ilike_pattern is not None:
        params["pattern"] = ilike_pattern

    results = []
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
        for rank, row in enumerate(rows, start=1):
            results.append({
                "rank"       : rank,
                "result_type": "table",
                "table_path" : row.table_path,
                "page_no"    : row.page_no,
                "header"     : row.header,
                "source"     : row.source,
                "document_id": row.document_id,
                "table_id"   : row.table_id,
            })

    # If no header match found, fall back to returning all tables for the document
    if not results:
        fallback_sql = f"""
            SELECT
                id          AS table_id,
                document_id AS document_id,
                source      AS source,
                header      AS header,
                page_no     AS page_no,
                table_path  AS table_path
            FROM   "tables"
            WHERE  1=1
                   {doc_filter}
            ORDER  BY page_no ASC
            LIMIT  :top_k
        """
        fallback_params: Dict[str, Any] = {"top_k": top_k}
        if document_id is not None:
            fallback_params["doc_id"] = document_id

        with engine.connect() as conn:
            rows = conn.execute(text(fallback_sql), fallback_params).fetchall()
            for rank, row in enumerate(rows, start=1):
                results.append({
                    "rank"       : rank,
                    "result_type": "table",
                    "table_path" : row.table_path,
                    "page_no"    : row.page_no,
                    "header"     : row.header,
                    "source"     : row.source,
                    "document_id": row.document_id,
                    "table_id"   : row.table_id,
                })

    print(f"[Retriever] Table search returned {len(results)} result(s).")
    return results


# ─────────────────────────────────────────────────────────────
# Image retrieval function
# ─────────────────────────────────────────────────────────────

def retrieve_images(
    query: str,
    top_k: int = 5,
    document_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve matching images from the `images` table and return their paths.

    Strategy
    --------
    1. Query the `images` table directly (no embeddings needed).
    2. Filter by document_id if provided.
    3. Match rows whose header text contains any word from the query
       (case-insensitive ILIKE search).
    4. Fall back to all images ordered by page_no if no header match found.

    Parameters
    ----------
    query : str
        Natural language query — used to match against the header column.
    top_k : int
        Maximum number of image results to return (default: 5).
    document_id : int | None
        If set, restricts search to a specific document only.

    Returns
    -------
    list[dict]
        Each dict contains:
          - rank        : result rank (1-indexed)
          - result_type : always 'image'
          - image_path  : filesystem path to the extracted image file
          - page_no     : page number where the image appears
          - header      : section header of the image
          - source      : source PDF path
          - document_id : parent document ID
          - image_id    : primary key of the images row
    """

    if not query or not query.strip():
        raise ValueError("Query cannot be empty.")

    top_k = min(max(1, top_k), 20)

    doc_filter = "AND document_id = :doc_id" if document_id is not None else ""

    # Build ILIKE pattern from the first meaningful word in the query
    import re
    words = [w for w in re.findall(r"\b\w{3,}\b", query.lower())]
    header_filter = ""
    ilike_pattern = None
    if words:
        ilike_pattern = f"%{words[0]}%"
        header_filter = "AND header ILIKE :pattern"

    sql = f"""
        SELECT
            id          AS image_id,
            document_id AS document_id,
            source      AS source,
            header      AS header,
            page_no     AS page_no,
            image_path  AS image_path
        FROM   images
        WHERE  1=1
               {doc_filter}
               {header_filter}
        ORDER  BY page_no ASC
        LIMIT  :top_k
    """

    params: Dict[str, Any] = {"top_k": top_k}
    if document_id is not None:
        params["doc_id"] = document_id
    if ilike_pattern is not None:
        params["pattern"] = ilike_pattern

    results = []
    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).fetchall()
        for rank, row in enumerate(rows, start=1):
            results.append({
                "rank"       : rank,
                "result_type": "image",
                "image_path" : row.image_path,
                "page_no"    : row.page_no,
                "header"     : row.header,
                "source"     : row.source,
                "document_id": row.document_id,
                "image_id"   : row.image_id,
            })

    # Fall back to all images if no header match
    if not results:
        fallback_sql = f"""
            SELECT
                id          AS image_id,
                document_id AS document_id,
                source      AS source,
                header      AS header,
                page_no     AS page_no,
                image_path  AS image_path
            FROM   images
            WHERE  1=1
                   {doc_filter}
            ORDER  BY page_no ASC
            LIMIT  :top_k
        """
        fallback_params: Dict[str, Any] = {"top_k": top_k}
        if document_id is not None:
            fallback_params["doc_id"] = document_id

        with engine.connect() as conn:
            rows = conn.execute(text(fallback_sql), fallback_params).fetchall()
            for rank, row in enumerate(rows, start=1):
                results.append({
                    "rank"       : rank,
                    "result_type": "image",
                    "image_path" : row.image_path,
                    "page_no"    : row.page_no,
                    "header"     : row.header,
                    "source"     : row.source,
                    "document_id": row.document_id,
                    "image_id"   : row.image_id,
                })

    print(f"[Retriever] Image search returned {len(results)} result(s).")
    return results
