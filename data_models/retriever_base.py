from pydantic import BaseModel, Field
from typing import List, Optional
from .retriever_measures import SearchMeasures, AccuracyMeasure

class RetrievedChunk(BaseModel):
    rank: int
    similarity: float
    chunk_text: str
    header: Optional[str]
    page_no: int
    source: str
    document_id: int
    filename: str
    vector_similarity: Optional[float] = None
    fts_similarity: Optional[float] = None
    rrf_score: Optional[float] = None
    measures: Optional[SearchMeasures] = None
    accuracy: Optional[AccuracyMeasure] = None



class IndexedDocument(BaseModel):
    document_id: int
    filename: str
    format: str
    indexed_at: str
    chunk_count: int


class StructuredAnswer(BaseModel):
    answer: str = Field(..., description="The main text answer to the user query, citing sources like [1], [2].")
    key_takeaways: List[str] = Field(default=[], description="Bullet points summarizing key takeaways from the answer.")
    suggested_followups: List[str] = Field(default=[], description="A list of 2-3 relevant follow-up questions the user might ask next.")
