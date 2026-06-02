from sqlalchemy import (
    Column,
    Integer,
    Text,
    ForeignKey,
    Index
)

from core.database import Base
from pgvector.sqlalchemy import Vector


class Embedding(Base):
    __tablename__ = "embeddings"

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

    chunk_text = Column(
        Text,
        nullable=False
    )

    header = Column(
        Text,
        nullable=True
    )

    page_no = Column(
        Integer,
        nullable=False,
        index=True,
        default=0
    )

    content_embedding = Column(
        Vector(1024),
        nullable=False
    )

    header_embedding = Column(
        Vector(1024),
        nullable=True
    )

    __table_args__ = (
        Index(
            "content_hnsw_idx",
            "content_embedding",
            postgresql_using="hnsw",
            postgresql_ops={
                "content_embedding": "vector_cosine_ops"
            }
        ),

        Index(
            "header_hnsw_idx",
            "header_embedding",
            postgresql_using="hnsw",
            postgresql_ops={
                "header_embedding": "vector_cosine_ops"
            }
        ),
    )