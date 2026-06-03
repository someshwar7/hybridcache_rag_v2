from sqlalchemy import (
    Column,
    Integer,
    Text,
    TIMESTAMP,
    UniqueConstraint,
    func
)
from core.database import Base


class UserAPIKey(Base):
    __tablename__ = "user_api_keys"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Text,
        nullable=False,
        index=True
    )

    provider = Column(
        Text,
        nullable=False,
        index=True  # 'groq', 'cohere', etc.
    )

    encrypted_key = Column(
        Text,
        nullable=False
    )

    created_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_provider_key"),
    )


class UserSetting(Base):
    __tablename__ = "user_settings"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Text,
        nullable=False,
        unique=True,
        index=True
    )

    active_provider = Column(
        Text,
        nullable=False,
        default="groq"  # default to groq
    )

    created_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        TIMESTAMP,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
