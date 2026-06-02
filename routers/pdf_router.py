import os
import sys
from contextlib import redirect_stdout
from fastapi import (
    APIRouter,
    UploadFile,
    File,
    Form,
    HTTPException
)
from service.file_metadata import get_total_pdf_pages
from preprocessing.docling_main import run_pipeline
from schemas.chunks_to_db import save_chunks_to_db
from helpers import validate_and_parse_pdf_selection
from data_models import PDFUploadResponse, PDFSelectionResponse
from logs.logs_router import active_logs, DualWriter
from service.session_manager import create_session, update_activity

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


@router.post("/upload-pdf", response_model=PDFUploadResponse)
async def upload_pdf_file(file: UploadFile = File(...)):
    """Receives and saves the uploaded PDF file, returning basic metadata"""
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Please upload a valid PDF file"
        )

    # Save uploaded file
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())

    # Retrieve page count details
    pdf_details = get_total_pdf_pages(file_path, return_file_name=True)
    assert isinstance(pdf_details, dict)

    # Generate and register a session for this upload
    session_id = create_session()

    # Create a database record immediately to track the upload for cleanup
    from core.database import SessionLocal
    from schemas.file_schema import FileResponse
    db = SessionLocal()
    try:
        original_filename = file.filename
        file_ext = os.path.splitext(original_filename)[-1].lstrip(".").lower() or "pdf"
        file_record = FileResponse(
            original_filename=original_filename,
            file_format=file_ext,
            session_id=session_id
        )
        db.add(file_record)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database record creation failed during upload: {e}")
    finally:
        db.close()

    return {
        "success": True,
        "data": {
            "file_name": pdf_details["file_name"],
            "total_pages": pdf_details["total_pages"],
            "pdf_path": file_path,
            "session_id": session_id
        }
    }


@router.post("/pdf-selection", response_model=PDFSelectionResponse)
def process_pdf_selection(
    pdf_path: str = Form(...),
    selection_mode: str = Form("all"),
    page_number: str = Form(None),
    start_page: str = Form(None),
    end_page: str = Form(None),
    page_list: str = Form(None),
    enable_verbose: bool = Form(True),
    session_id: str = Form(None)
):
    """Executes the rendering, extraction, and semantic chunking pipeline"""
    
    # Update activity for this session if it exists
    if session_id:
        update_activity(session_id)

    # --- Input Validation and Parsing ---
    (
        api_selection_mode,
        parsed_page_number,
        parsed_start_page,
        parsed_end_page,
        parsed_page_list
    ) = validate_and_parse_pdf_selection(
        selection_mode=selection_mode,
        page_number=page_number,
        start_page=start_page,
        end_page=end_page,
        page_list=page_list
    )

    # --- Run Pipeline with Logs Captured ---
    active_logs.clear()
    
    dual_writer = DualWriter(sys.stdout)

    try:
        with redirect_stdout(dual_writer):
            final_chunks, rendered_data, paths = run_pipeline(
                base_dir=os.getcwd(),
                pdf_path=pdf_path,
                visualize=False,
                overlap_chars=200,
                dpi=150,
                selection_mode=api_selection_mode,
                page_number=parsed_page_number,
                start_page=parsed_start_page,
                end_page=parsed_end_page,
                page_list=parsed_page_list,
                enable_verbose=enable_verbose,
                session_id=session_id
            )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # --- Persist chunks + embeddings to PostgreSQL ---
    # Saves: files, raw_text, images, tables, embeddings rows
    try:
        document_id = save_chunks_to_db(
            pdf_path=pdf_path,
            final_chunks=final_chunks,
            verbose=print,
            session_id=session_id
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Pipeline succeeded but DB persist failed: {e}"
        )

    verbose_logs = list(active_logs)
    selected_pages = [page["page_number"] for page in rendered_data]

    # --- Assemble API Response ---
    return {
        "success": True,
        "document_id": document_id,
        "pdf_path": pdf_path,
        "selection_mode": selection_mode,
        "selected_pages": selected_pages,
        "rendered_pages": rendered_data,
        "final_chunks": final_chunks,
        "verbose_logs": verbose_logs,
        "enable_verbose": enable_verbose,
        "session_id": session_id
    }
