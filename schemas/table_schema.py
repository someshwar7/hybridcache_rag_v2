from sqlalchemy import (
    Column,
    Integer,
    Text,
    TIMESTAMP,
    ForeignKey,
    func
)

from core.database import Base


class TableData(Base):
    __tablename__ = "tables"

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
        nullable=False,
        index=True
    )

    header = Column(
        Text,
        nullable=True
    )

    page_no = Column(
        Integer,
        nullable=False,
        index=True
    )

    table_path = Column(
        Text,
        nullable=False
    )

    created_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        nullable=False,
        index=True
    )