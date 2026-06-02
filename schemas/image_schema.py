from sqlalchemy import (
    Column,
    Integer,
    Text,
    TIMESTAMP,
    func
)
from sqlalchemy import ForeignKey
from core.database import Base


class Image(Base):
    __tablename__ = "images"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    document_id = Column(
        Integer,
        ForeignKey("files.id"),
        nullable=False,
        index=True
    )

    source = Column(
        Text,
        index=True,
        nullable=False
    )

    header = Column(
        Text,
        nullable=True
    )

    page_no = Column(
        Integer,
        index=True,
        nullable=False
    )

    image_path = Column(
        Text,
        nullable=False
    )

    created_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        index=True,
        nullable=False
    )