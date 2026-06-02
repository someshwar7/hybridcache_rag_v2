import os
from typing import Optional
from pdf_render import render_pdf_pages, convert_rendered_pages_to_base64
from docling_visualizer import run_docling_visualization
from docling_extractor import run_docling_extraction

import matplotlib.pyplot as plt

# ==========================================
# HELPERS
# ==========================================
def verbose(msg, enable=True):
    if enable:
        print(f"[INFO] {msg}")


# ==========================================
# MAIN PIPELINE
# ==========================================
def run_pipeline(
    base_dir: str,
    book_name: str     = "book.pdf",
    visualize: bool    = False,
    overlap_chars: int = 200,
    dpi: int           = 150,
    selection_mode: str = "all",
    page_number: Optional[int]    = None,
    start_page: Optional[int]     = None,
    end_page: Optional[int]       = None,
    page_list: Optional[list]     = None,
    enable_verbose: bool = True,
    pdf_path: Optional[str]       = None,
    session_id: Optional[str]     = None,
):
    # ----------------------------------------
    # OUTPUT FOLDERS
    # ----------------------------------------
    preprocessed_dir = os.path.join(base_dir, "preprocessed_data")
    if session_id:
        image_dir        = os.path.join(preprocessed_dir, "imagefolder", session_id)
        table_dir        = os.path.join(preprocessed_dir, "tablefolder", session_id)
        raw_dir          = os.path.join(preprocessed_dir, "raw_data", session_id)
    else:
        image_dir        = os.path.join(preprocessed_dir, "imagefolder")
        table_dir        = os.path.join(preprocessed_dir, "tablefolder")
        raw_dir          = os.path.join(preprocessed_dir, "raw_data")

    os.makedirs(image_dir, exist_ok=True)
    os.makedirs(table_dir, exist_ok=True)
    os.makedirs(raw_dir,   exist_ok=True)

    verbose(f"Output folders ready -> {preprocessed_dir}", enable_verbose)

    # ----------------------------------------
    # PDF PATH
    # ----------------------------------------
    if not pdf_path:
        pdf_path = os.path.join(base_dir, book_name)
    verbose(f"PDF path -> {pdf_path}", enable_verbose)

    # ----------------------------------------
    # CELL 1 — RENDER PDF PAGES
    # Frontend Driven Parameters
    # ----------------------------------------

    rendered_pages, selected_pages = render_pdf_pages(

        pdf_path=pdf_path,

        # Defaults
        dpi=dpi if dpi else 150,

        selection_mode=selection_mode if selection_mode else "all",

        # Optional Parameters
        page_number=page_number,
        start_page=start_page,
        end_page=end_page,
        page_list=page_list,

        # Default Verbose = True
        enable_verbose=enable_verbose if enable_verbose is not None else True
    )

    verbose(
        f"render_pdf_pages returned {len(selected_pages)} page(s): {selected_pages}",
        enable_verbose
    )

    # # ----------------------------------------
    # # CELL 2 — DOCLING VISUALIZATION (optional)
    # # ----------------------------------------
    # if visualize:
    #     figures = run_docling_visualization(
    #         pdf_path=pdf_path,
    #         selected_pages=selected_pages,
    #         rendered_pages=rendered_pages,
    #         verbose=verbose,
    #     )

    #     if not figures:
    #         print("[WARN] No figures returned. Check selected_pages/rendered_pages")
    #     else:
    #         for page_num, fig in figures:
    #             print(f"[INFO] Displaying Page {page_num}")

    #     plt.show()

    # ----------------------------------------
    # CELL 3 — DOCLING EXTRACTION & CHUNKING
    # ----------------------------------------
    final_chunks = run_docling_extraction(
        pdf_path=pdf_path,
        selected_pages=selected_pages,
        overlap_chars=overlap_chars,
        image_dir=image_dir,
        table_dir=table_dir,
        raw_dir=raw_dir,
        verbose=lambda msg: verbose(msg, enable_verbose),
    )

    # Convert rendered pages to base64 format for frontend
    rendered_data = convert_rendered_pages_to_base64(rendered_pages, selected_pages)

    # ----------------------------------------
    # SUMMARY
    # ----------------------------------------
    print(f"\nTotal Chunks : {len(final_chunks)}")
    print(f"\n{'='*60}\n")

    return final_chunks, rendered_data, {
        "preprocessed_dir": preprocessed_dir,
        "image_dir"       : image_dir,
        "table_dir"       : table_dir,
        "raw_dir"         : raw_dir,
    }