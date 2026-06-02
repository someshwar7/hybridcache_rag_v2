from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TableBase(BaseModel):
    document_id: int
    source: str
    header: Optional[str] = None
    page_no: int
    table_path: str


class TableCreate(TableBase):
    pass


class TableResponse(TableBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
