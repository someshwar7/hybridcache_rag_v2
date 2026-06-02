import fitz
from PIL import Image
import numpy as np
import io
import time
import base64


def verbose(message, enable_verbose=True):
    if enable_verbose:
        print(f"[INFO] {message}")
        time.sleep(0.3)


def render_pdf_pages(
    pdf_path,dpi=150,
    selection_mode="all",
    page_number=None,
    start_page=None,
    end_page=None,
    page_list=None,
    enable_verbose=True
):
    verbose("Initializing PDF processing system...", enable_verbose)

    doc = fitz.open(pdf_path)

    verbose("PDF loaded successfully", enable_verbose)

    total_pages = len(doc)

    verbose(f"Total pages detected: {total_pages}", enable_verbose)

    selected_pages = []

    # ---------------------------------------------------
    # Selection Logic
    # ---------------------------------------------------

    if selection_mode == "single":

        if page_number is None:
            raise ValueError("page_number is required for single mode")

        if 1 <= page_number <= total_pages:
            selected_pages = [page_number]
        else:
            raise ValueError("Invalid page number")

    elif selection_mode == "range":

        if start_page is None or end_page is None:
            raise ValueError("start_page and end_page are required for range mode")

        if (
            1 <= start_page <= total_pages
            and 1 <= end_page <= total_pages
            and start_page <= end_page
        ):
            selected_pages = list(range(start_page, end_page + 1))
        else:
            raise ValueError("Invalid page range")

    elif selection_mode == "list":

        if page_list is None:
            raise ValueError("page_list is required for list mode")

        selected_pages = [
            p for p in page_list
            if 1 <= p <= total_pages
        ]

        if not selected_pages:
            raise ValueError("No valid pages found")

    elif selection_mode == "all":

        selected_pages = list(range(1, total_pages + 1))

    else:
        raise ValueError("Invalid selection_mode")

    verbose(
        f"{len(selected_pages)} page(s) added for processing",
        enable_verbose
    )

    # ---------------------------------------------------
    # Rendering Pipeline
    # ---------------------------------------------------

    rendered_pages = {}

    for idx, page_num in enumerate(selected_pages, start=1):

        verbose(
            f"Rendering page {page_num} ({idx}/{len(selected_pages)})",
            enable_verbose
        )

        fitz_page = doc[page_num - 1]

        pix = fitz_page.get_pixmap(dpi=dpi)

        rendered_pages[page_num] = {

            # Raw PyMuPDF Pixmap
            "pix": pix,

            # Coordinate scaling
            "scale_x": pix.width / fitz_page.rect.width,
            "scale_y": pix.height / fitz_page.rect.height,

            # NumPy image
            "image": np.frombuffer(
                pix.samples,
                dtype=np.uint8
            ).reshape(pix.height, pix.width, pix.n),

            # PIL image
            "pil_image": Image.open(
                io.BytesIO(pix.tobytes("png"))
            )
        }

        verbose(
            f"Page {page_num} rendered successfully",
            enable_verbose
        )

    verbose("Page rendering pipeline complete", enable_verbose)

    return rendered_pages, selected_pages


def convert_rendered_pages_to_base64(rendered_pages, selected_pages):
    rendered_data = []
    for page_num in selected_pages:
        if page_num in rendered_pages:
            page_info = rendered_pages[page_num]
            pix = page_info["pix"]
            png_bytes = pix.tobytes("png")
            base64_img = base64.b64encode(png_bytes).decode("utf-8")
            rendered_data.append({
                "page_number": page_num,
                "base64_image": base64_img,
                "width": pix.width,
                "height": pix.height
            })
    return rendered_data