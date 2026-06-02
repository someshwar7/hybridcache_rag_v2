import sys
from fastapi import APIRouter

router = APIRouter()

active_logs = []


class DualWriter:
    """Helper stream writer to copy prints to both sys.stdout and log list"""
    def __init__(self, console_stream):
        self.console = console_stream

    def write(self, message: str) -> int:
        self.console.write(message)
        msg_str = message.strip()
        if msg_str:
            active_logs.append(msg_str)
        return len(message)

    def flush(self):
        self.console.flush()


@router.get("/stream-logs")
async def stream_active_logs():
    """Returns the current buffered verbose logs in real-time"""
    return {"logs": active_logs}


# Setup separate query monitor logger
import os
import logging

LOGS_DIR = os.path.dirname(os.path.abspath(__file__))
log_file_path = os.path.join(LOGS_DIR, "query_monitor.log")

query_logger = logging.getLogger("query_monitor")
query_logger.setLevel(logging.INFO)

if not query_logger.handlers:
    # File Handler
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_formatter)
    query_logger.addHandler(file_handler)
    
    # Stream Handler (Stdout console logs)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(file_formatter)
    query_logger.addHandler(console_handler)


# Setup separate API call and rate limit logger
api_log_file_path = os.path.join(LOGS_DIR, "logger.log")

api_logger = logging.getLogger("api_logger")
api_logger.setLevel(logging.INFO)

if not api_logger.handlers:
    # File Handler
    api_file_handler = logging.FileHandler(api_log_file_path, encoding="utf-8")
    api_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    api_file_handler.setFormatter(api_formatter)
    api_logger.addHandler(api_file_handler)
    
    # Stream Handler (Stdout console logs)
    api_console_handler = logging.StreamHandler(sys.stdout)
    api_console_handler.setFormatter(api_formatter)
    api_logger.addHandler(api_console_handler)


