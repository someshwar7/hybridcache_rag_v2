"""
embeddings.py
-------------
Generates text embeddings using the Cohere API (free trial).

Model   : embed-english-v3.0
Dims    : 1024
Input   : list of strings
Output  : list[list[float]] (1024-dim per text)

Usage:
    from core.embeddings import get_embeddings
    vectors = get_embeddings(["hello world", "another chunk"])
"""

import os
from typing import List

import cohere
from dotenv import load_dotenv
from logs.logs_router import api_logger

load_dotenv()

# ─────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────
EMBEDDING_MODEL = "embed-english-v3.0"   # Free trial supported
EMBEDDING_DIMS  = 1024                   # Dimensions produced by v3.0
INPUT_TYPE      = "search_document"      # Use "search_query" when querying

from service.byok_service import provider_manager, KeyNotFoundError
from core.database import SessionLocal
from sqlalchemy.orm import Session

def get_cohere_client(session_id: Optional[str] = None, db: Optional[Session] = None) -> cohere.Client:
    """
    Dynamically retrieves the Cohere client for the given session.
    Falls back to COHERE_API_KEY in the environment if not configured by the user.
    """
    opened_db = False
    if db is None:
        db = SessionLocal()
        opened_db = True
    try:
        if session_id:
            try:
                return provider_manager.get_client(db, session_id, "cohere")
            except KeyNotFoundError:
                pass
        cohere_env = os.getenv("COHERE_API_KEY")
        if cohere_env:
            return cohere.Client(api_key=cohere_env)
        raise KeyNotFoundError("No Cohere API key configured. Please upload a Cohere API key.")
    finally:
        if opened_db:
            db.close()


def get_embeddings(
    texts: List[str],
    input_type: str = INPUT_TYPE,
    session_id: Optional[str] = None,
    db: Optional[Session] = None
) -> List[List[float]]:
    """
    Generate embeddings for a list of text strings using Cohere API.
    """
    cleaned = [t if t and t.strip() else " " for t in texts]

    try:
        client = get_cohere_client(session_id, db)
        api_logger.info(f"Initiating Cohere Embedding API Call - Model: {EMBEDDING_MODEL}, Chunks: {len(cleaned)}")
        response = client.embed(
            texts=cleaned,
            model=EMBEDDING_MODEL,
            input_type=input_type,
        )
        api_logger.info("Cohere Embedding API Call Success")
        return [list(vec) for vec in response.embeddings]
    except Exception as e:
        err_msg = str(e)
        if "rate limit" in err_msg.lower() or "429" in err_msg:
            api_logger.warning(f"Cohere Embedding API Rate Limit Hit! Detail: {err_msg}")
        else:
            api_logger.error(f"Cohere Embedding API Call Failed: {err_msg}")
        raise


def get_single_embedding(
    text: str,
    input_type: str = INPUT_TYPE,
    session_id: Optional[str] = None,
    db: Optional[Session] = None
) -> List[float]:
    """
    Generate a single embedding for one text string.
    """
    return get_embeddings([text], input_type=input_type, session_id=session_id, db=db)[0]

