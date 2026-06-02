import os
import sys
import json
from pathlib import Path

# Resolve parent directory to allow correct imports when running standalone
PARENT_DIR = Path(__file__).resolve().parent.parent
if str(PARENT_DIR) not in sys.path:
    sys.path.insert(0, str(PARENT_DIR))
if str(PARENT_DIR / "preprocessing") not in sys.path:
    sys.path.insert(0, str(PARENT_DIR / "preprocessing"))

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Import other routers to wire up the full application on port 1800
from logs.ui_router import router as ui_router
from logs.logs_router import router as logs_router
from routers import pdf_router
from routers import retriever_retrieve, retriever_answer, retriever_classify
from routers import db_router, preprocessed_router

router = APIRouter(prefix="/test", tags=["Test"])

@router.get("/", response_class=FileResponse)
def get_test_ui():
    """
    Serves the main frontend dashboard for testing.
    """
    return FileResponse(str(PARENT_DIR / "ui" / "index.html"))

# =====================================================================
# STANDALONE FASTAPI APP
# =====================================================================
app = FastAPI(title="HybridCache RAG v2 Test Backend", version="2.0.0")

# Setup CORS middleware
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files folder
app.mount("/ui", StaticFiles(directory=str(PARENT_DIR / "ui")), name="ui")

# Register all routers so that the frontend code runs fully standalone on port 1800
app.include_router(ui_router)
app.include_router(logs_router)
app.include_router(pdf_router)
app.include_router(retriever_retrieve)
app.include_router(retriever_answer)
app.include_router(retriever_classify)
app.include_router(db_router)
app.include_router(preprocessed_router)
app.include_router(router)
