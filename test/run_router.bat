@echo off
echo Starting Standalone Test Router...

:: Launch browser to the Inline UI and Swagger UI docs
start "" "http://127.0.0.1:1800/test/"
start "" "http://127.0.0.1:1800/docs"

:: Start Uvicorn running the app instance in router.py
..\.venv\Scripts\uvicorn router:app --reload --port 1800

pause
