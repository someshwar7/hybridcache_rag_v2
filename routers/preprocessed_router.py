import os
from pathlib import Path
from fastapi import APIRouter, HTTPException

# Resolve parent directory to locate folders correctly
PARENT_DIR = Path(__file__).resolve().parent.parent

router = APIRouter(prefix="/preprocessed", tags=["Preprocessed Data"])

@router.post("/clear-cache")
def clear_preprocessed_cache():
    """
    Dynamically traverses the preprocessed_data folder, listing all subfolders
    and deleting all contents inside them without deleting the subfolders themselves.
    """
    preprocessed_dir = os.path.join(PARENT_DIR, "preprocessed_data")
    cleared_count = 0
    failed = []
    
    if os.path.exists(preprocessed_dir) and os.path.isdir(preprocessed_dir):
        for item in os.listdir(preprocessed_dir):
            subfolder_path = os.path.join(preprocessed_dir, item)
            if os.path.isdir(subfolder_path):
                for filename in os.listdir(subfolder_path):
                    file_path = os.path.join(subfolder_path, filename)
                    try:
                        if os.path.isfile(file_path) or os.path.islink(file_path):
                            os.remove(file_path)
                            cleared_count += 1
                        elif os.path.isdir(file_path):
                            import shutil
                            shutil.rmtree(file_path)
                            cleared_count += 1
                    except Exception as e:
                        failed.append(f"{item}/{filename}: {str(e)}")
                        
    if failed:
        raise HTTPException(
            status_code=500, 
            detail=f"Partially cleared. Failed to remove: {', '.join(failed)}"
        )
        
    return {
        "status": "success",
        "message": f"Preprocessed folders cleared successfully (folders preserved). Cleared {cleared_count} items."
    }
