"""
docling_extractor.py
--------------------
Extracts structured content from selected PDF pages using Docling.
Handles text, images, tables, semantic chunking, and overlapping.
Call run_docling_extraction() from main.py after render_pdf_pages().
"""

import json
import os

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat


MARKDOWN_FORMAT = {
    "TitleItem"        : lambda t: f"# {t}",
    "SectionHeaderItem": lambda t: f"## {t}",
    "ListItem"         : lambda t: f"- {t}",
    "FormulaItem"      : lambda t: f"$$\n{t}\n$$",
    "CodeItem"         : lambda t: f"```\n{t}\n```",
    "TextItem"         : lambda t: t,
    "PictureItem"      : lambda t: "",
    "TableItem"        : lambda t: t,
}


def run_docling_extraction(
    pdf_path: str,
    selected_pages: list,
    image_dir: str     = "imagefolder",
    table_dir: str     = "tablefolder",
    raw_dir: str       = "raw_data",
    overlap_chars: int = 200,
    verbose=print,
):
    """
    Extract and semantically chunk content from selected PDF pages.

    Parameters
    ----------
    pdf_path : str
        Path to the original PDF (e.g. "book.pdf").
    selected_pages : list[int]
        1-based page numbers to process (from render_pdf_pages).
    image_dir : str
        Folder to save extracted images (default: "imagefolder").
    table_dir : str
        Folder to save extracted tables (default: "tablefolder").
    overlap_chars : int
        Number of trailing characters to carry into the next chunk (default: 200).
    verbose : callable
        Logging function (default: print).

    Returns
    -------
    final_chunks : list[dict]
        Semantically chunked content with overlap applied.
    structured_json : list[dict]
        Raw per-item extraction records.
    """

    # ----------------------------------------
    # SAFETY CHECK
    # ----------------------------------------
    if not selected_pages:
        raise RuntimeError("selected_pages is empty. Run render_pdf_pages() first.")

    # ----------------------------------------
    # OUTPUT FOLDERS
    # ----------------------------------------
    os.makedirs(image_dir, exist_ok=True)
    os.makedirs(table_dir, exist_ok=True)
    os.makedirs(raw_dir,   exist_ok=True)

    # ----------------------------------------
    # DOCLING SETUP
    # ----------------------------------------
    verbose("Initializing Docling semantic pipeline...")

    pipeline_options = PdfPipelineOptions()
    pipeline_options.images_scale            = 2.0
    pipeline_options.generate_picture_images = True

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )

    verbose("Docling ready")

    # ----------------------------------------
    # PROCESS PAGES
    # ----------------------------------------
    image_id      = 0
    table_id      = 0
    structured_json = []

    for idx, page_num in enumerate(selected_pages, start=1):

        verbose(f"Processing page {page_num} ({idx}/{len(selected_pages)})")

        result     = converter.convert(pdf_path, page_range=(page_num, page_num))
        doc_parsed = result.document

        for item, level in doc_parsed.iterate_items():

            item_class = item.__class__.__name__
            text       = (getattr(item, "text", "") or "").strip()

            markdown_text = MARKDOWN_FORMAT.get(
                item_class, lambda t: t
            )(text)

            # --- Image handling ---
            image_path = None
            if item_class == "PictureItem":
                image_id      += 1
                image_filename = f"image_p{page_num}_{image_id}.png"
                image_path     = os.path.join(image_dir, image_filename)
                try:
                    extracted_image = item.get_image(doc_parsed)
                    if extracted_image is not None:
                        extracted_image.save(image_path)
                        verbose(f"Image saved -> {image_filename}")
                    else:
                        verbose(f"No image data on page {page_num}")
                        image_path = None
                except Exception as e:
                    print(f"[WARNING] Image save failed page {page_num}: {e}")
                    image_path = None

            # --- Table handling ---
            table_path = None
            if item_class == "TableItem":
                table_id      += 1
                table_filename = f"table_p{page_num}_{table_id}.md"
                table_path     = os.path.join(table_dir, table_filename)
                try:
                    markdown_text = item.export_to_markdown(doc_parsed)
                    with open(table_path, "w", encoding="utf-8") as tf:
                        tf.write(markdown_text)
                    verbose(f"Table saved -> {table_filename}")
                except Exception as e:
                    print(f"[WARNING] Table save failed page {page_num}: {e}")
                    table_path = None

            # --- Append record ---
            structured_json.append({
                "source"     : pdf_path,
                "page_number": page_num,
                "content"    : {
                    "type"      : item_class,
                    "label"     : str(getattr(item, "label", "")),
                    "page"      : page_num,
                    "content_md": markdown_text,
                    "image"     : image_path,
                    "table"     : table_path,
                }
            })

    verbose("Raw extraction complete")

    # ----------------------------------------
    # SEMANTIC CHUNKING — header based
    # ----------------------------------------
    verbose("Starting semantic chunking pipeline...")

    chunks         = []
    current_chunk  = []
    current_header = None

    for record in structured_json:

        item_type  = record["content"]["type"]
        content_md = record["content"]["content_md"]
        page       = record["page_number"]
        image      = record["content"]["image"]
        table      = record["content"]["table"]

        if item_type == "SectionHeaderItem":
            if current_chunk:
                chunks.append({
                    "header" : current_header,
                    "page"   : current_chunk[0]["page"],
                    "content": "\n\n".join(
                        c["content_md"] for c in current_chunk if c["content_md"]
                    ),
                    "images" : [c["image"] for c in current_chunk if c["image"]],
                    "tables" : [c["table"] for c in current_chunk if c["table"]],
                })
            current_header = content_md
            current_chunk  = []
        else:
            current_chunk.append({
                "page"      : page,
                "content_md": content_md,
                "image"     : image,
                "table"     : table,
            })

    # Flush last chunk
    if current_chunk:
        chunks.append({
            "header" : current_header,
            "page"   : current_chunk[0]["page"],
            "content": "\n\n".join(
                c["content_md"] for c in current_chunk if c["content_md"]
            ),
            "images" : [c["image"] for c in current_chunk if c["image"]],
            "tables" : [c["table"] for c in current_chunk if c["table"]],
        })

    verbose(f"{len(chunks)} semantic chunks created")

    # ----------------------------------------
    # OVERLAPPING
    # ----------------------------------------
    verbose(f"Applying overlap of {overlap_chars} chars...")

    final_chunks = []

    for i, chunk in enumerate(chunks):
        if i == 0:
            final_chunks.append({
                "source"     : pdf_path,
                "page_number": chunk["page"],
                "content"    : {
                    "header" : chunk["header"],
                    "page"   : chunk["page"],
                    "content": chunk["content"],
                    "images" : chunk["images"],
                    "tables" : chunk["tables"],
                }
            })
            continue

        prev_tail = chunks[i - 1]["content"][-overlap_chars:]
        final_chunks.append({
            "source"     : pdf_path,
            "page_number": chunk["page"],
            "content"    : {
                "header" : chunk["header"],
                "page"   : chunk["page"],
                "content": prev_tail + "\n\n" + chunk["content"],
                "images" : chunk["images"],
                "tables" : chunk["tables"],
            }
        })

    verbose(f"Overlap applied to {len(final_chunks)} chunks")
    verbose("Pipeline completed successfully")

    # ----------------------------------------
    # SAVE FINAL CHUNKS JSON
    # ----------------------------------------
    base = os.getcwd()

    def to_rel(path):
        if path is None:
            return None
        try:
            return os.path.relpath(path, base).replace("\\", "/")
        except ValueError:
            return path

    for chunk in final_chunks:
        chunk["source"] = to_rel(chunk["source"])
        chunk["content"]["images"] = [to_rel(p) for p in chunk["content"]["images"]]
        chunk["content"]["tables"] = [to_rel(p) for p in chunk["content"]["tables"]]

    chunks_json_path = os.path.join(raw_dir, "final_chunks.json")
    with open(chunks_json_path, "w", encoding="utf-8") as f:
        json.dump(final_chunks, f, indent=2, ensure_ascii=False)
    verbose(f"Final chunks saved -> {chunks_json_path}")

    return final_chunks