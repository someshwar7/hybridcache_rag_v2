import sys
import os
import json
from pathlib import Path
from dotenv import load_dotenv

# Resolve paths
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "preprocessing"))

load_dotenv()

from service.session_manager import redis_client, clear_redis_cache
from core.retriever import retrieve_chunks
from core.hybrid_retriever import retrieve_hybrid_chunks

def run_cache_tests():
    if not redis_client:
        print("ERROR: Redis is not connected. Caching tests cannot run.")
        sys.exit(1)

    print("=" * 80)
    print("RUNNING REDIS CACHING TESTS")
    print("=" * 80)

    # 1. Clear any existing cache first
    clear_redis_cache()
    print("[Test] Cache cleared.")

    # 2. Test standard retrieve caching
    query = "What projects are listed?"
    print(f"\n[Test] Running first query (retrieve_chunks) for: '{query}'")
    
    # Check keys in Redis before running query
    keys_before = redis_client.keys("cache:*")
    print(f"   Redis keys before query: {keys_before}")

    # First retrieval (goes to DB)
    res1 = retrieve_chunks(query=query, top_k=3, use_reranker=False)
    print(f"   First retrieval returned {len(res1)} chunks.")

    # Check keys in Redis after running query
    keys_after = redis_client.keys("cache:*")
    print(f"   Redis keys after query: {keys_after}")
    assert len(keys_after) > 0, "No cache key was written to Redis!"

    # Second retrieval (should hit Redis cache)
    print(f"\n[Test] Running second query (retrieve_chunks) for: '{query}'")
    res2 = retrieve_chunks(query=query, top_k=3, use_reranker=False)
    print(f"   Second retrieval returned {len(res2)} chunks.")

    # Validate equality
    assert len(res1) == len(res2), "Result length mismatch between DB and Cache!"
    for c1, c2 in zip(res1, res2):
        assert c1["chunk_text"] == c2["chunk_text"], "Chunk text mismatch!"
    print("   -> Success: Cache hit and values matched perfectly.")

    # 3. Test hybrid retrieve caching
    print(f"\n[Test] Running first query (retrieve_hybrid_chunks) for: '{query}'")
    h_res1 = retrieve_hybrid_chunks(query=query, top_k=3)
    print(f"   First hybrid retrieval returned {len(h_res1)} chunks.")

    # Second hybrid retrieval (should hit Redis cache)
    print(f"\n[Test] Running second query (retrieve_hybrid_chunks) for: '{query}'")
    h_res2 = retrieve_hybrid_chunks(query=query, top_k=3)
    print(f"   Second hybrid retrieval returned {len(h_res2)} chunks.")

    assert len(h_res1) == len(h_res2), "Hybrid result length mismatch!"
    for c1, c2 in zip(h_res1, h_res2):
        assert c1["chunk_text"] == c2["chunk_text"], "Hybrid chunk text mismatch!"
    print("   -> Success: Hybrid Cache hit and values matched perfectly.")

    # 4. Test cache invalidation via clear_redis_cache
    print("\n[Test] Testing cache invalidation...")
    clear_redis_cache()
    keys_post_clear = redis_client.keys("cache:*")
    print(f"   Redis keys after clear_redis_cache: {keys_post_clear}")
    assert len(keys_post_clear) == 0, "Keys were not fully cleared!"
    print("   -> Success: Cache invalidation successfully cleared all cache keys.")

    print("\n" + "=" * 80)
    print("ALL REDIS CACHING TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    run_cache_tests()
