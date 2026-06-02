from sqlalchemy import (
    create_engine,
    text
)

from sqlalchemy.orm import (
    sessionmaker,
    declarative_base
)

DATABASE_URL = (
    "postgresql://postgres:1812@localhost:5432/developer_db"
)

engine = create_engine(DATABASE_URL)


with engine.connect() as conn:
    conn.execute(
        text("CREATE EXTENSION IF NOT EXISTS vector")
    )
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