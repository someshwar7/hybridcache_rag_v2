import os
import sys
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# =====================================================================
# PATH CONFIGURATION
# =====================================================================
# Add preprocessing directory to python sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "preprocessing"))

# Import routers
from logs.ui_router import router as ui_router
from logs.logs_router import router as logs_router
from routers import pdf_router, retriever_retrieve, retriever_answer, retriever_classify, db_router, preprocessed_router
from test.router import router as test_router
from service.session_manager import cleanup_expired_sessions

# =====================================================================
# BACKGROUND CLEANUP TASK & LIFESPAN CONFIGURATION
# =====================================================================
async def session_cleanup_loop():
    """Background loop to clean up expired session assets and DB records every 60 seconds."""
    while True:
        try:
            # Cleanup sessions inactive for > 10 minutes (600 seconds)
            cleanup_expired_sessions(threshold_seconds=600)
        except Exception as e:
            import logging
            logging.getLogger("main").error(f"Error in session cleanup task: {e}")
        await asyncio.sleep(60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Launch background worker task
    cleanup_task = asyncio.create_task(session_cleanup_loop())
    yield
    # Shutdown: Cleanly cancel background worker task
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

# =====================================================================
# FASTAPI APP & INTERFACE CONFIGURATION
# =====================================================================
app = FastAPI(title="HybridCache RAG v2 Backend", version="2.0.0", lifespan=lifespan)

# Setup CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files folder
app.mount("/ui", StaticFiles(directory="ui"), name="ui")

# Register routers
app.include_router(ui_router)
app.include_router(logs_router)
app.include_router(pdf_router)
app.include_router(retriever_retrieve)
app.include_router(retriever_answer)
app.include_router(retriever_classify)
app.include_router(db_router)
app.include_router(preprocessed_router)
app.include_router(test_router)