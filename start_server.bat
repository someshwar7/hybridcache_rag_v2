@echo off

echo Starting FastAPI Server...

:: Automatically open the web browser
start "" "http://localhost:1800/"

:: Run using the local virtual environment's uvicorn
.venv\Scripts\uvicorn main:app --reload --port 1800

pause