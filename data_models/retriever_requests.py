from pydantic import BaseModel, Field
from typing import Optional

class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language search query")
    top_k: int = Field(default=5, ge=1, le=20, description="Number of results to return")
    document_id: Optional[int] = Field(default=None, description="Filter by specific document ID")
    min_similarity: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum similarity threshold")
    use_reranker: bool = Field(default=True, description="Whether to use Cohere Reranker to re-rank results")
    session_id: Optional[str] = Field(default=None, description="Session ID to track user activity")
