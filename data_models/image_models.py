from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ImageBase(BaseModel):
    document_id: int
    source: str
    header: Optional[str] = None
    page_no: int
    image_path: str


class ImageCreate(ImageBase):
    pass


class ImageResponse(ImageBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
