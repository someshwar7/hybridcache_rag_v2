"""
docling_visualizer.py
---------------------
Wraps the Docling bounding-box pipeline as a reusable function.
Call run_docling_visualization() from main.py after render_pdf_pages().
"""

from docling.document_converter import DocumentConverter
import matplotlib.pyplot as plt
import matplotlib.patches as patches


CLASS_COLORS = {
    "TextItem":          "red",
    "SectionHeaderItem": "blue",
    "PictureItem":       "green",
    "TableItem":         "orange",
    "ListItem":          "purple",
    "FormulaItem":       "cyan",
}


def run_docling_visualization(
    pdf_path: str,
    selected_pages: list,
    rendered_pages: dict,
    verbose=print,
):
    """
    Run Docling on each selected page and overlay bounding boxes.

    Parameters
    ----------
    pdf_path : str
        Path to the original PDF (e.g. "book.pdf").
    selected_pages : list[int]
        1-based page numbers to process (from render_pdf_pages).
    rendered_pages : dict
        Keyed by page number. Each value must contain:
            - "pix"     : fitz.Pixmap
            - "scale_x" : float
            - "scale_y" : float
            - "image"   : np.ndarray (RGB)
    verbose : callable
        Logging function (default: print).
    """

    # ----------------------------------------
    # SAFETY CHECK
    # ----------------------------------------
    if not selected_pages:
        raise RuntimeError("selected_pages is empty. Run render_pdf_pages() first.")
    if not rendered_pages:
        raise RuntimeError("rendered_pages is empty. Run render_pdf_pages() first.")

    # ----------------------------------------
    # DOCLING SETUP
    # ----------------------------------------
    verbose("Initializing Docling converter...")
    converter = DocumentConverter()
    verbose("Docling converter ready")

    # ----------------------------------------
    # PROCESS EACH SELECTED PAGE
    # ----------------------------------------
    verbose("Starting Docling processing pipeline...")

    figures = []

    for idx, page_num in enumerate(selected_pages, start=1):

        verbose(f"Docling parsing page {page_num} ({idx}/{len(selected_pages)})")

        # --- Docling parse ---
        result     = converter.convert(pdf_path, page_range=(page_num, page_num))
        doc_parsed = result.document
        verbose(f"Page {page_num} parsed successfully")

        # --- Fetch rendered data ---
        pix     = rendered_pages[page_num]["pix"]
        scale_x = rendered_pages[page_num]["scale_x"]
        scale_y = rendered_pages[page_num]["scale_y"]
        image   = rendered_pages[page_num]["image"]

        # --- Plot ---
        fig, ax = plt.subplots(figsize=(12, 16))
        ax.imshow(image)
        ax.axis("off")
        ax.set_title(f"PDF Page {page_num} — Docling Elements", fontsize=13)

        seen = {}

        for item, _ in doc_parsed.iterate_items():
            if not hasattr(item, "prov") or not item.prov:
                continue

            for prov in item.prov:
                if prov.page_no != page_num or prov.bbox is None:
                    continue

                b     = prov.bbox
                label = item.__class__.__name__
                color = CLASS_COLORS.get(label, "red")

                coord_origin = getattr(b, "coord_origin", None)

                if coord_origin is not None and "BOTTOMLEFT" in str(coord_origin).upper():
                    x = b.l * scale_x
                    y = pix.height - (b.b * scale_y)
                    w = (b.r - b.l) * scale_x
                    h = (b.b - b.t) * scale_y
                else:
                    x = b.l * scale_x
                    y = b.t * scale_y
                    w = (b.r - b.l) * scale_x
                    h = (b.b - b.t) * scale_y

                ax.add_patch(patches.Rectangle(
                    (x, y), w, h,
                    linewidth=2,
                    edgecolor=color,
                    facecolor=color,
                    alpha=0.10
                ))

                ax.text(
                    x + 2, y + 2,
                    label.replace("Item", ""),
                    fontsize=6,
                    color="white",
                    fontweight="bold",
                    verticalalignment="top",
                    clip_on=True,
                    bbox=dict(boxstyle="square,pad=0.2", fc=color, ec="none", alpha=0.85)
                )

                seen[label] = color

        ax.legend(
            handles=[
                patches.Patch(facecolor=c, edgecolor=c, label=l.replace("Item", ""))
                for l, c in seen.items()
            ],
            loc="lower right", fontsize=9,
            framealpha=0.95,
            title="Element type", title_fontsize=9
        )

        plt.tight_layout()
        figures.append((page_num, fig))

        verbose(f"Page {page_num} bounding boxes rendered successfully")

    verbose("Docling pipeline execution completed successfully")
    return figures