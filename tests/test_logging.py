import sys
import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv

# Resolve paths
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "preprocessing"))

load_dotenv()

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def run_logging_tests():
    query_monitor_path = ROOT_DIR / "logs" / "query_monitor.log"
    logger_path = ROOT_DIR / "logs" / "logger.log"

    # Clean existing logs if any to ensure clean test state
    if query_monitor_path.exists():
        query_monitor_path.write_text("", encoding="utf-8")
    if logger_path.exists():
        logger_path.write_text("", encoding="utf-8")

    print("=" * 80)
    print("RUNNING LOGGING AND API MONITORING TESTS")
    print("=" * 80)

    # 1. Test /retriever/answer logging
    test_query_1 = "Test logging query for answer endpoint 123"
    print(f"\n[Test] Sending Query to /retriever/answer: '{test_query_1}'")
    response1 = client.post("/retriever/answer", json={
        "query": test_query_1,
        "session_id": "test_log_session",
        "top_k": 3
    })
    assert response1.status_code == 200, f"Request failed: {response1.text}"

    # 2. Test /retriever/retrieve logging
    test_query_2 = "Test logging query for retrieve endpoint 456"
    print(f"\n[Test] Sending Query to /retriever/retrieve: '{test_query_2}'")
    response2 = client.post("/retriever/retrieve", json={
        "query": test_query_2,
        "session_id": "test_log_session",
        "top_k": 3
    })
    assert response2.status_code == 200, f"Request failed: {response2.text}"

    # Wait a moment for file logs to flush
    time.sleep(1)

    # 3. Verify query_monitor.log contains both queries
    assert query_monitor_path.exists(), "query_monitor.log was not created!"
    query_log_content = query_monitor_path.read_text(encoding="utf-8")
    print("\n[query_monitor.log contents]:")
    print(query_log_content)

    assert f"Processing query: {test_query_1}" in query_log_content, "Query 1 missing from query_monitor.log"
    assert f"Processing query: {test_query_2}" in query_log_content, "Query 2 missing from query_monitor.log"
    print("-> Success: Incoming queries logged correctly in query_monitor.log!")

    # 4. Verify logger.log contains API call log entries
    assert logger_path.exists(), "logger.log was not created!"
    api_log_content = logger_path.read_text(encoding="utf-8")
    print("\n[logger.log contents]:")
    print(api_log_content)

    assert "Initiating Groq Chat Completion API Call" in api_log_content or "Initiating Groq Intent Classification API Call" in api_log_content, "API Call logs missing from logger.log"
    print("-> Success: API calls logged correctly in logger.log!")

    print("\n" + "=" * 80)
    print("ALL LOGGING AND API MONITORING TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    run_logging_tests()
