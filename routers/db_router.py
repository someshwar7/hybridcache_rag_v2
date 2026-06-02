import os
from pathlib import Path
from fastapi import APIRouter, HTTPException
from core.database import SessionLocal
from schemas.file_schema import FileResponse as FileSchema
from schemas.image_schema import Image
from schemas.table_schema import TableData
from schemas.text_schema import RawText
from schemas.embedding_schems import Embedding

# Resolve parent directory to locate uploads folder correctly
PARENT_DIR = Path(__file__).resolve().parent.parent

router = APIRouter(prefix="/db", tags=["Database"])

@router.post("/flush")
def flush_database():
    """
    Deletes all indexed document metadata, chunks, tables, images, and embeddings
    from the database without modifying table schemas or column names.
    Clears the uploads folder as well.
    """
    db = SessionLocal()
    try:
        # Delete rows in dependent tables first (foreign keys check)
        db.query(Embedding).delete()
        db.query(RawText).delete()
        db.query(Image).delete()
        db.query(TableData).delete()
        db.query(FileSchema).delete()
        db.commit()
        
        # Clear Redis query cache on flush
        try:
            from service.session_manager import clear_redis_cache
            clear_redis_cache()
        except Exception:
            pass
        
        # Clean up files in the uploads folder
        uploads_dir = os.path.join(PARENT_DIR, "uploads")
        if os.path.exists(uploads_dir):
            for filename in os.listdir(uploads_dir):
                file_path = os.path.join(uploads_dir, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                except Exception:
                    pass

        return {
            "status": "success",
            "message": "Database flushed and cleared successfully (table schemas preserved)."
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to flush database: {str(e)}")
    finally:
        db.close()

