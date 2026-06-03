import os
from dotenv import load_dotenv

# Ensure environment variables from .env are loaded before retrieving DATABASE_URL
load_dotenv()

from sqlalchemy import (
    create_engine,
    text
)

from sqlalchemy.orm import (
    sessionmaker,
    declarative_base
)

pg_user = os.getenv("POSTGRES_USER", "postgres")
pg_pass = os.getenv("POSTGRES_PASSWORD", "postgres")
pg_db = os.getenv("POSTGRES_DB", "developer_db")
pg_port = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"postgresql://{pg_user}:{pg_pass}@127.0.0.1:{pg_port}/{pg_db}"
)


engine = create_engine(DATABASE_URL)



with engine.connect() as conn:
    conn.execute(
        text("CREATE EXTENSION IF NOT EXISTS vector")
    )
    # Check if files table exists first
    table_exists = conn.execute(text(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='files')"
    )).scalar()
    
    if table_exists:
        # Check if files table has session_id column; if not, add it
        res = conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='files' AND column_name='session_id'"
        )).fetchone()
        if not res:
            conn.execute(text("ALTER TABLE files ADD COLUMN session_id TEXT"))
    conn.commit()


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    """
    FastAPI dependency that provides a SQLAlchemy database session.
    Ensures that the session is closed automatically when the request finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()