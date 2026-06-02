"""
test.py
-------
Integration tests for FastAPI retriever router endpoints using TestClient.
Renders specific output structures for RAG, WEB, and LLM query routes.
Plain-ASCII print outputs to prevent encoding errors on standard Windows consoles.
"""

import sys
from pathlib import Path

# Resolve paths to allow correct imports when running from terminal
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "preprocessing"))
sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

test_queries = [
    "i need a summary of the table presented in page number 108",
    "Who won the latest Formula 1 Grand Prix?",
    "Write a python function to merge two lists",
    "What projects are listed?",
    "provide some links related to space"
]


def run_router_tests():
    print("Testing FastAPI Route: /retriever/classify")
    print("=" * 80)

    for query in test_queries:
        print(f"\n> Sending Query: '{query}'")
        response = client.post("/retriever/classify", json={"query": query})

        if response.status_code == 200:
            payload = response.json()
            if isinstance(payload, dict):
                data = payload.get('data')
                if isinstance(data, dict):
                    route = str(data.get('intent', '')).upper()  # RAG, WEB_SEARCH, or DIRECT_LLM
                    explanation = data.get('explanation', '')
                    results_list = data.get("results")
                    results = results_list if isinstance(results_list, list) else []

                    print(f"   Response Status : SUCCESS ({response.status_code})")
                    print(f"   Classified Route: {route}")
                    print(f"   Explanation     : {explanation}")
                    print("   Output Details  :")

                    if route == "RAG":
                        # Render top 3 RAG chunks
                        print(f"     [Top {min(3, len(results))} Chunks retrieved]")
                        for i, r in enumerate(results[:3], start=1):
                            if isinstance(r, dict):
                                title = r.get("document_title") or r.get("filename") or "Unknown Document"
                                page = r.get("page_no", "?")
                                text_preview = r.get("chunk_text", "")
                                print(f"     {i}. Page {page} | Document: {title}")
                                print(f"        Content: {text_preview}...")

                    elif route == "WEB_SEARCH":
                        # Render top 3 web links
                        print(f"     [Top {min(3, len(results))} Web Links retrieved]")
                        for i, r in enumerate(results[:3], start=1):
                            if isinstance(r, dict):
                                link = r.get("source") or "No link provided"
                                title = r.get("filename") or r.get("header") or "Web Page"
                                print(f"     {i}. Link : {link}")
                                print(f"        Title: {title}")

                    elif route == "DIRECT_LLM":
                        # Render top 3 points (key takeaways)
                        first_chunk = results[0] if (results and results[0] is not None) else {}
                        mock_chunk = first_chunk if isinstance(first_chunk, dict) else {}
                        takeaways = mock_chunk.get("key_takeaways", [])
                        
                        print("     [Top 3 Key Points Generated]")
                        if isinstance(takeaways, list) and takeaways:
                            for i, pt in enumerate(takeaways[:3], start=1):
                                print(f"     * Point {i}: {pt}")
                        else:
                            # Fallback to splitting standard answer text if takeaways are not populated
                            answer_text = mock_chunk.get("chunk_text", "")
                            sentences = [s.strip() for s in answer_text.split(".") if s.strip()]
                            for i, pt in enumerate(sentences[:3], start=1):
                                print(f"     * Point {i}: {pt}.")
        else:
            print(f"   Response Status : FAILED ({response.status_code})")
            print(f"   Error Detail    : {response.text}")
        print("-" * 80)


if __name__ == "__main__":
    run_router_tests()