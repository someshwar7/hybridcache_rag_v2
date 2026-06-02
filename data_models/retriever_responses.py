from pydantic import BaseModel
from typing import List
from .retriever_base import RetrievedChunk, IndexedDocument

class RetrieveResponse(BaseModel):
    success: bool
    query: str
    total_results: int
    results: List[RetrievedChunk]


class DocumentListResponse(BaseModel):
    success: bool
    total: int
    documents: List[IndexedDocument]


class StructuredAnswerResponse(BaseModel):
    success: bool
    query: str
    results: List[RetrievedChunk]
    answer: str
    key_takeaways: List[str]
    suggested_followups: List[str]
