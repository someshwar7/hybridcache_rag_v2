from typing import Optional
from fastapi import HTTPException


def validate_and_parse_pdf_selection(
    selection_mode: str,
    page_number: Optional[str] = None,
    start_page: Optional[str] = None,
    end_page: Optional[str] = None,
    page_list: Optional[str] = None
):
    """
    Validates selection mode inputs and parses page parameters into expected types.
    Returns:
        tuple: (api_selection_mode, parsed_page_number, parsed_start_page, parsed_end_page, parsed_page_list)
    """
    def parse_int(val):
        if val is None or val == "" or val.lower() == "null":
            return None
        try:
            return int(val)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid integer value: {val}"
            )

    api_selection_mode = selection_mode
    if selection_mode == "custom":
        api_selection_mode = "list"

    parsed_page_number = None
    parsed_start_page = None
    parsed_end_page = None
    parsed_page_list = None

    if api_selection_mode == "single":
        parsed_page_number = parse_int(page_number)
        if parsed_page_number is None:
            raise HTTPException(status_code=400, detail="page_number is required for single page mode")
            
    elif api_selection_mode == "range":
        parsed_start_page = parse_int(start_page)
        parsed_end_page = parse_int(end_page)
        if parsed_start_page is None or parsed_end_page is None:
            raise HTTPException(status_code=400, detail="start_page and end_page are required for range mode")

    elif api_selection_mode == "list":
        if page_list is None or page_list == "" or page_list.lower() == "null":
            raise HTTPException(status_code=400, detail="page_list is required for custom pages mode")
        try:
            parsed_page_list = [int(p.strip()) for p in page_list.split(",") if p.strip()]
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid page list format. Must be comma-separated integers."
            )

    return (
        api_selection_mode,
        parsed_page_number,
        parsed_start_page,
        parsed_end_page,
        parsed_page_list
    )
