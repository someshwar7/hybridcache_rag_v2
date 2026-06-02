from typing import Union, Dict, Any
from pypdf import PdfReader
import os


def get_total_pdf_pages(
    pdf_path: str,
    return_file_name: bool = False
) -> Union[Dict[str, Any], int]:

    reader = PdfReader(pdf_path)

    total_pages = len(reader.pages)

    if return_file_name:

        file_name = os.path.basename(pdf_path)

        return {
            "file_name": file_name,
            "total_pages": total_pages
        }

    return total_pages