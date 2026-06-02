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
from service.session_manager import redis_client, clear_redis_cache

client = TestClient(app)

def run_memory_tests():
    if not redis_client:
        print("ERROR: Redis is not connected. Chat memory tests cannot run.")
        sys.exit(1)

    print("=" * 80)
    print("RUNNING REDIS CHAT MEMORY TESTS")
    print("=" * 80)

    # 1. Clear any existing cache/history first
    clear_redis_cache()
    
    session_id = "test_memory_session_123"
    history_key = f"history:{session_id}"
    
    # Clean up test session keys in Redis if they exist
    redis_client.delete(history_key)
    print(f"[Test] Using session_id: {session_id}")

    # 2. Tell the assistant our name
    q1 = "My name is Som"
    print(f"\n[Test] Sending Query 1: '{q1}'")
    response1 = client.post("/retriever/answer", json={
        "query": q1,
        "session_id": session_id,
        "top_k": 3
    })
    
    assert response1.status_code == 200, f"Query 1 failed: {response1.text}"
    
    # Find the payload from chunk lines
    payload = None
    for line in response1.text.split("\n"):
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                if data.get("type") == "result":
                    payload = data.get("payload")
            except:
                pass
                
    assert payload is not None, "Did not receive a result event payload!"
    print(f"   Response 1: {payload.get('answer')}")

    # Check that history is stored in Redis
    history_len = redis_client.llen(history_key)
    print(f"   Redis history list size: {history_len} messages.")
    assert history_len == 2, "Redis did not store exactly 2 messages (user + assistant)!"
    
    raw_history = redis_client.lrange(history_key, 0, -1)
    print(f"   Redis stored messages: {[json.loads(m) for m in raw_history]}")

    # 3. Ask the assistant what our name is
    q2 = "what is my name ?"
    print(f"\n[Test] Sending Query 2 (which should retrieve name from history): '{q2}'")
    response2 = client.post("/retriever/answer", json={
        "query": q2,
        "session_id": session_id,
        "top_k": 3
    })
    
    assert response2.status_code == 200, f"Query 2 failed: {response2.text}"
    
    payload2 = None
    for line in response2.text.split("\n"):
        if line.startswith("data: "):
            try:
                data = json.loads(line[6:])
                if data.get("type") == "result":
                    payload2 = data.get("payload")
            except:
                pass
                
    assert payload2 is not None, "Did not receive a result event payload for Query 2!"
    answer2 = payload2.get('answer')
    print(f"   Response 2: {answer2}")
    
    # Assert that the name "Som" is present in the response
    assert "som" in answer2.lower(), f"Did not recall the name 'Som'! Answer: {answer2}"
    print("   -> Success: The model successfully recalled the name from conversational history stored in Redis!")

    # 4. Cleanup
    redis_client.delete(history_key)
    print("\n" + "=" * 80)
    print("ALL REDIS CHAT MEMORY TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    run_memory_tests()
