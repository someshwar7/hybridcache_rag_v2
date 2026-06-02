from sqlalchemy import (
    Column,
    Integer,
    Text,
    TIMESTAMP,
    func
)

from core.database import Base


class FileResponse(Base):
    __tablename__ = "files"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    original_filename = Column(
        Text,
        nullable=False
    )

    file_format = Column(
        Text,
        nullable=False,
        index=True
    )

    created_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        nullable=False,
        index=True
    )

    session_id = Column(
        Text,
        nullable=True,
        index=True
    )