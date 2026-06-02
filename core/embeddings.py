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
COHERE_API_KEY  = os.getenv("COHERE_API_KEY")
EMBEDDING_MODEL = "embed-english-v3.0"   # Free trial supported
EMBEDDING_DIMS  = 1024                   # Dimensions produced by v3.0
INPUT_TYPE      = "search_document"      # Use "search_query" when querying


if not COHERE_API_KEY:
    raise EnvironmentError(
        "COHERE_API_KEY not found in environment. "
        "Please add it to your .env file."
    )

_client = cohere.Client(api_key=COHERE_API_KEY)


def get_embeddings(
    texts: List[str],
    input_type: str = INPUT_TYPE
) -> List[List[float]]:
    """
    Generate embeddings for a list of text strings using Cohere API.

    Parameters
    ----------
    texts : list[str]
        List of text strings to embed. Empty strings are replaced
        with a single space to avoid API errors.
    input_type : str
        "search_document" for indexing, "search_query" for querying.

    Returns
    -------
    list[list[float]]
        List of 1024-dimensional float vectors, one per input text.
    """

    # Cohere rejects empty strings - replace with whitespace
    cleaned = [t if t and t.strip() else " " for t in texts]

    try:
        api_logger.info(f"Initiating Cohere Embedding API Call - Model: {EMBEDDING_MODEL}, Chunks: {len(cleaned)}")
        response = _client.embed(
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
    input_type: str = INPUT_TYPE
) -> List[float]:
    """
    Generate a single embedding for one text string.

    Parameters
    ----------
    text : str
        Text string to embed.
    input_type : str
        "search_document" for indexing, "search_query" for querying.

    Returns
    -------
    list[float]
        A 1024-dimensional float vector.
    """
    return get_embeddings([text], input_type=input_type)[0]
