from pydantic import BaseModel
from typing import List, Optional


class PDFUploadData(BaseModel):
    file_name: str
    total_pages: int
    pdf_path: str
    session_id: Optional[str] = None


class PDFUploadResponse(BaseModel):
    success: bool
    data: PDFUploadData


class RenderedPage(BaseModel):
    page_number: int
    base64_image: str
    width: int
    height: int


class ChunkContent(BaseModel):
    header: Optional[str]
    page: int
    content: str
    images: List[str]
    tables: List[str]


class SemanticChunk(BaseModel):
    source: str
    page_number: int
    content: ChunkContent


class PDFSelectionResponse(BaseModel):
    success: bool
    document_id: int
    pdf_path: str
    selection_mode: str
    selected_pages: List[int]
    rendered_pages: List[RenderedPage]
    final_chunks: List[SemanticChunk]
    verbose_logs: List[str]
    enable_verbose: bool
    session_id: Optional[str] = None
