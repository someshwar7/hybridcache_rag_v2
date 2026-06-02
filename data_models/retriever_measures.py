from pydantic import BaseModel
from typing import Optional

class SearchMeasures(BaseModel):
    bm25_raw: Optional[float] = None
    vector_raw: Optional[float] = None
    bm25_norm: Optional[float] = None
    vector_norm: Optional[float] = None
    score_pct: Optional[float] = None


class AccuracyMeasure(BaseModel):
    overall_accuracy: float
    confidence_label: Optional[str] = None

