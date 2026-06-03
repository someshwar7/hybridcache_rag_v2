import os
import uuid
import shutil
import logging
import redis
from typing import Dict, Any, List, Optional
from sqlalchemy import text

from core.database import SessionLocal
from schemas.file_schema import FileResponse
from schemas.image_schema import Image
from schemas.table_schema import TableData
from schemas.text_schema import RawText
from schemas.embedding_schems import Embedding

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("session_manager")

# Resolve Base Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREPROCESSED_DIR = os.path.join(BASE_DIR, "preprocessed_data")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")

# Connect to local Redis instance
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", None)

try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True
    )
    # Verify connectivity
    redis_client.ping()
    logger.info(f"Successfully connected to Redis at redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}")
except Exception as e:
    logger.error(f"Failed to connect to Redis at redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}: {e}")
    redis_client = None


def create_session(session_id: Optional[str] = None) -> str:
    """
    Generates a unique session ID if not provided, registers it in Redis
    with a 600-second TTL (10 minutes), and returns it.
    """
    if not session_id:
        session_id = str(uuid.uuid4())

    key = f"session:{session_id}"
    if redis_client:
        try:
            # Set key with 600 seconds expiration (10 minutes)
            redis_client.setex(key, 600, "active")
            logger.info(f"Session {session_id} registered in Redis with 600s TTL.")
        except Exception as e:
            logger.error(f"Failed to save session {session_id} in Redis: {e}")
    else:
        logger.error("Redis client not initialized. Cannot register session.")

    return session_id


def update_activity(session_id: Optional[str]):
    """
    Refreshes the TTL of the session in Redis back to 600 seconds.
    If the session key is missing, it is recreated.
    """
    if not session_id:
        return

    key = f"session:{session_id}"
    if redis_client:
        try:
            if redis_client.exists(key):
                redis_client.expire(key, 600)
                logger.info(f"Refreshed TTL for session {session_id} to 600s.")
            else:
                # Key expired or evicted; recreate it
                redis_client.setex(key, 600, "active")
                logger.warning(f"Recreated missing session key for session {session_id} in Redis with 600s TTL.")
            
            # Refresh history key TTL if it exists
            history_key = f"history:{session_id}"
            if redis_client.exists(history_key):
                redis_client.expire(history_key, 600)
                logger.info(f"Refreshed TTL for chat history of session {session_id} to 600s.")
        except Exception as e:
            logger.error(f"Failed to refresh session activity in Redis: {e}")
    else:
        logger.error("Redis client not initialized. Cannot refresh session activity.")


def _cleanup_single_session(session_id: str):
    """
    Deletes the session directories and all database entries associated with a session.
    """
    logger.info(f"[Cleanup] Cleaning up expired session {session_id}...")

    # 1. Database cleanup
    db = SessionLocal()
    try:
        # Find all files associated with this session_id
        files = db.query(FileResponse).filter(FileResponse.session_id == session_id).all()

        for file_rec in files:
            doc_id = file_rec.id
            filename = file_rec.original_filename
            logger.info(f"[Cleanup] Deleting DB records for File ID {doc_id} ({filename}) for session {session_id}")

            # Cascade delete in proper dependency order
            db.query(Embedding).filter(Embedding.document_id == doc_id).delete()
            db.query(RawText).filter(RawText.document_id == doc_id).delete()
            db.query(Image).filter(Image.document_id == doc_id).delete()
            db.query(TableData).filter(TableData.document_id == doc_id).delete()
            db.delete(file_rec)

            # Delete physical uploaded file
            uploaded_pdf = os.path.join(UPLOADS_DIR, filename)
            if os.path.exists(uploaded_pdf):
                try:
                    os.remove(uploaded_pdf)
                    logger.info(f"[Cleanup] Deleted physical file: {uploaded_pdf}")
                except Exception as ex:
                    logger.error(f"[Cleanup] Failed to delete uploaded file {uploaded_pdf}: {ex}")

        db.commit()
        logger.info(f"[Cleanup] DB records cleared for session {session_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"[Cleanup] Database error cleaning up session {session_id}: {e}")
    finally:
        db.close()

    # 1.5. Redis chat history cleanup
    if redis_client:
        try:
            redis_client.delete(f"history:{session_id}")
            logger.info(f"[Cleanup] Deleted Redis chat history for session {session_id}")
        except Exception as rex:
            logger.error(f"[Cleanup] Failed to delete Redis history for session {session_id}: {rex}")

    # 2. On-disk directory cleanup
    folders_to_delete = [
        os.path.join(PREPROCESSED_DIR, "imagefolder", session_id),
        os.path.join(PREPROCESSED_DIR, "tablefolder", session_id),
        os.path.join(PREPROCESSED_DIR, "raw_data", session_id)
    ]

    for folder in folders_to_delete:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder, ignore_errors=True)
                logger.info(f"[Cleanup] Deleted directory: {folder}")
            except Exception as ex:
                logger.error(f"[Cleanup] Failed to delete folder {folder}: {ex}")

    logger.info(f"[Cleanup] Session {session_id} fully cleaned up.")


def cleanup_expired_sessions(threshold_seconds: int = 600):
    """
    Performs active scanning to detect expired sessions:
    1. Queries all unique session_ids currently in the PostgreSQL files table.
    2. Checks if each session_id key exists in Redis.
    3. If a session key does not exist in Redis (meaning it has expired),
       fully purges its physical folder assets and DB records.
    """
    if not redis_client:
        logger.error("Redis client is not available. Skipping session cleanup check.")
        return

    logger.info("[Cleanup] Checking for expired sessions via Redis active scanner...")

    db = SessionLocal()
    unique_db_sessions = []
    try:
        results = db.query(FileResponse.session_id).distinct().filter(
            FileResponse.session_id != None
        ).all()
        unique_db_sessions = [row[0] for row in results if row[0]]
    except Exception as e:
        logger.error(f"Error querying active sessions from files table: {e}")
    finally:
        db.close()

    if not unique_db_sessions:
        logger.info("[Cleanup] No active document sessions tracked in database.")
        return

    logger.info(f"[Cleanup] Found {len(unique_db_sessions)} active document sessions in DB. Checking Redis status...")

    expired_sessions = []
    for sid in unique_db_sessions:
        key = f"session:{sid}"
        try:
            # If the session key does not exist in Redis, it has expired
            if not redis_client.exists(key):
                expired_sessions.append(sid)
        except Exception as e:
            logger.error(f"Error checking Redis key existence for session {sid}: {e}")

    if not expired_sessions:
        logger.info("[Cleanup] All database document sessions are still active in Redis.")
        return

    logger.info(f"[Cleanup] Detected {len(expired_sessions)} expired sessions to purge: {expired_sessions}")
    for sid in expired_sessions:
        try:
            _cleanup_single_session(sid)
        except Exception as e:
            logger.error(f"[Cleanup] Error cleaning up session {sid}: {e}")


def clear_redis_cache():
    """
    Clears all query caches (cache:*) from Redis.
    """
    if redis_client:
        try:
            keys = redis_client.keys("cache:*")
            if keys:
                redis_client.delete(*keys)
                logger.info(f"[Redis Cache] Successfully cleared {len(keys)} cached keys.")
            else:
                logger.info("[Redis Cache] No keys to clear in cache.")
        except Exception as e:
            logger.error(f"[Redis Cache] Failed to clear keys: {e}")

