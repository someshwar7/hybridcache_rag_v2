"""
helpers/prompt_loader.py
------------------------
Utility to dynamically load system prompt templates from the templates directory
using pathlib.
"""

from pathlib import Path

# Resolve project root relative to this file
ROOT_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT_DIR / "templates"


def load_template(filename: str) -> str:
    """
    Load the contents of a template file from the templates directory.

    Parameters
    ----------
    filename : str
        Name of the template file (e.g. 'router_prompt.txt').

    Returns
    -------
    str
        Contents of the template file.
    """
    file_path = TEMPLATES_DIR / filename
    if not file_path.exists():
        raise FileNotFoundError(f"Template not found at: {file_path}")

    return file_path.read_text(encoding="utf-8")
