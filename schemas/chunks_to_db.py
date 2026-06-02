"""
chunks_to_db.py
---------------
Maps the final_chunks variable (already saved as JSON) to the database
using the SQLAlchemy schemas defined in the schemas directory.

Flow:
  JSON Output  <- docling_extractor.py (final_chunks.json on disk)
  DB Output    <- this module (chunks_to_db.py), writes to PostgreSQL

Schema Mapping from final_chunks:
  FileResponse  -> one record per PDF file
  RawText       -> chunk.content.content  (text body per chunk)
  Image         -> chunk.content.images   (one row per image path)
  TableData     -> chunk.content.tables   (one row per table path)
  Embedding     -> chunk.content.content + chunk.content.header
                   converted to real 1024-dim Cohere vectors via
                   core.embeddings.get_embeddings()

Embedding strategy:
  - All content + header texts are collected first (one pass over chunks)
  - A single batched call to get_embeddings() converts every text at once
  - Each Embedding row receives:
      content_embedding : 1024-dim vector from chunk text body
      header_embedding  : 1024-dim vector from header (nullable if absent)
"""

import os
from typing import List, Dict, Any, Optional

from core.database import SessionLocal
from core.embeddings import get_embeddings, EMBEDDING_DIMS
from schemas.file_schema import FileResponse
from schemas.image_schema import Image
from schemas.table_schema import TableData
from schemas.text_schema import RawText
from schemas.embedding_schems import Embedding


# ─────────────────────────────────────────────────────────────
# Internal helper
# ─────────────────────────────────────────────────────────────

def _embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Wrapper around get_embeddings() using 'search_document' input type,
    which is the correct mode when indexing content into a vector store.
    """
    return get_embeddings(texts, input_type="search_document")


# ─────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────

def save_chunks_to_db(
    pdf_path: str,
    final_chunks: List[Dict[str, Any]],
    verbose=print,
    session_id: Optional[str] = None
) -> int:

    db = SessionLocal()

    try:
        if session_id:
            # Check if a database record for this session already exists (e.g. created during upload)
            original_filename = os.path.basename(pdf_path)
            file_record = db.query(FileResponse).filter(
                FileResponse.session_id == session_id,
                FileResponse.original_filename == original_filename
            ).first()

            if not file_record:
                file_ext = os.path.splitext(original_filename)[-1].lstrip(".").lower() or "pdf"
                file_record = FileResponse(
                    original_filename=original_filename,
                    file_format=file_ext,
                    session_id=session_id
                )
                db.add(file_record)
                db.commit()  # Auto-assigns ID via Postgres serial column
            
            document_id = file_record.id
            verbose(f"[DB] Session-based file record verified -> ID: {document_id} | {original_filename} | Session: {session_id}")
        else:
            # ─────────────────────────────────────────────
            # 0. STRICT SLOT SHIFT & EVICTION (IDs [1, 2])
            # ─────────────────────────────────────────────
            # Step A: Evict document at ID 2 if it exists
            oldest_file = db.query(FileResponse).filter(FileResponse.id == 2).first()
            if oldest_file:
                verbose(f"[Eviction] Evicting document at ID 2: {oldest_file.original_filename}")
                db.query(Embedding).filter(Embedding.document_id == 2).delete()
                db.query(RawText).filter(RawText.document_id == 2).delete()
                db.query(Image).filter(Image.document_id == 2).delete()
                db.query(TableData).filter(TableData.document_id == 2).delete()
                
                try:
                    fp = os.path.join("uploads", oldest_file.original_filename)
                    if os.path.exists(fp):
                        os.remove(fp)
                        verbose(f"[Eviction] Deleted physical file: {fp}")
                except Exception as ex:
                    verbose(f"[Eviction Warning] Could not delete physical file: {ex}")
                    
                db.delete(oldest_file)
                db.commit()

            # Step B: Shift document at ID 1 to ID 2 if it exists
            newest_file = db.query(FileResponse).filter(FileResponse.id == 1).first()
            if newest_file:
                verbose(f"[Shift] Shifting document ID 1 ({newest_file.original_filename}) to ID 2")
                shifted_file = FileResponse(
                    id=2,
                    original_filename=newest_file.original_filename,
                    file_format=newest_file.file_format,
                    created_at=newest_file.created_at
                )
                db.add(shifted_file)
                db.commit()

                db.query(Embedding).filter(Embedding.document_id == 1).update({"document_id": 2})
                db.query(RawText).filter(RawText.document_id == 1).update({"document_id": 2})
                db.query(Image).filter(Image.document_id == 1).update({"document_id": 2})
                db.query(TableData).filter(TableData.document_id == 1).update({"document_id": 2})
                db.commit()

                db.delete(newest_file)
                db.commit()
                verbose("[Shift] Shift completed. Slot 1 is now empty.")

            # ─────────────────────────────────────────────
            # 1. FILE RECORD  →  FileResponse with ID 1
            # ─────────────────────────────────────────────
            original_filename = os.path.basename(pdf_path)
            file_ext = os.path.splitext(original_filename)[-1].lstrip(".").lower() or "pdf"

            file_record = FileResponse(
                id=1,
                original_filename=original_filename,
                file_format=file_ext
            )
            db.add(file_record)
            db.commit()  # Commit to reserve ID 1
            document_id = 1
            verbose(f"[DB] File record created -> ID: {document_id} | {original_filename}")

        # ─────────────────────────────────────────────
        # 2. COLLECT TEXTS FOR BATCH EMBEDDING
        #    Pass 1: gather content + header texts
        #    so we can embed them all in one API call.
        # ─────────────────────────────────────────────
        # Each entry: (text_body, header_or_None)
        chunk_text_pairs: List[tuple] = []

        for chunk in final_chunks:
            content   = chunk.get("content", {})
            text_body = content.get("content", "").strip()
            header    = (content.get("header") or "").strip() or None
            chunk_text_pairs.append((text_body, header))

        # Build a flat list of all texts to embed (skip truly empty bodies)
        # We embed content only when text_body is non-empty.
        flat_texts: List[str]          = []   # all texts sent to Cohere
        flat_index: List[tuple]        = []   # (chunk_idx, "content"|"header")

        for i, (text_body, header) in enumerate(chunk_text_pairs):
            if text_body:
                flat_texts.append(text_body)
                flat_index.append((i, "content"))
            if header:
                flat_texts.append(header)
                flat_index.append((i, "header"))

        # ─────────────────────────────────────────────
        # 3. SINGLE BATCHED EMBEDDING CALL
        # ─────────────────────────────────────────────
        content_vecs: Dict[int, Optional[List[float]]] = {}
        header_vecs:  Dict[int, Optional[List[float]]] = {}

        if flat_texts:
            verbose(f"[Embed] Generating embeddings for {len(flat_texts)} texts "
                    f"across {len(final_chunks)} chunks ...")
            all_vectors = _embed_texts(flat_texts)

            for (chunk_idx, role), vec in zip(flat_index, all_vectors):
                if role == "content":
                    content_vecs[chunk_idx] = vec
                else:
                    header_vecs[chunk_idx] = vec

            verbose(f"[Embed] Done — {len(all_vectors)} vectors ({EMBEDDING_DIMS}-dim each)")

        # ─────────────────────────────────────────────
        # 4. PER-CHUNK DB ROWS  →  RawText / Image / TableData / Embedding
        # ─────────────────────────────────────────────
        for i, chunk in enumerate(final_chunks):
            source    = chunk.get("source", pdf_path)
            page_no   = chunk.get("page_number", 0)
            content   = chunk.get("content", {})

            header     = (content.get("header") or "").strip() or None
            text_body  = content.get("content", "").strip()
            images     = content.get("images", [])
            tables     = content.get("tables", [])

            # ── RawText (raw_text table) ──────────────
            if text_body:
                db.add(RawText(
                    document_id=document_id,
                    source=source,
                    header=header,
                    page_no=page_no,
                    content=text_body
                ))

            # ── Image rows (images table) ─────────────
            for img_path in images:
                if img_path:
                    db.add(Image(
                        document_id=document_id,
                        source=source,
                        header=header,
                        page_no=page_no,
                        image_path=img_path
                    ))

            # ── TableData rows (tables table) ─────────
            for tbl_path in tables:
                if tbl_path:
                    db.add(TableData(
                        document_id=document_id,
                        source=source,
                        header=header,
                        page_no=page_no,
                        table_path=tbl_path
                    ))

            # ── Embedding (embeddings table) ──────────
            # Only insert an embedding row when we have a content vector.
            c_vec = content_vecs.get(i)
            h_vec = header_vecs.get(i)

            if c_vec is not None:
                db.add(Embedding(
                    document_id=document_id,
                    chunk_text=text_body,
                    header=header,
                    page_no=page_no,
                    content_embedding=c_vec,   # 1024-dim from Cohere
                    header_embedding=h_vec     # 1024-dim or None
                ))

        db.commit()
        verbose(f"[DB] All chunks committed successfully (Doc ID: {document_id})")
        try:
            from service.session_manager import clear_redis_cache
            clear_redis_cache()
        except Exception as e:
            verbose(f"[Redis Cache Error] Invalidation failed: {e}")
        return document_id

    except Exception as e:
        db.rollback()
        verbose(f"[DB ERROR] Rollback triggered: {e}")
        raise e

    finally:
        db.close()
