"""
core/web_search.py
------------------
Online web search fallback using Tavily Search API.
"""

import os
import requests
from typing import List, Dict, Any
from logs.logs_router import api_logger

def search_tavily(query: str) -> List[Dict[str, Any]]:
    """
    Perform a web search using the Tavily API.
    Returns results formatted like retriever pgvector chunks.
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        print("[Web Search] Warning: TAVILY_API_KEY not found in environment.")
        return []

    try:
        api_logger.info(f"Initiating Tavily Web Search API Call for query: {query}")
        response = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": 5
            },
            timeout=8
        )
        if response.status_code == 200:
            api_logger.info("Tavily Web Search API Call Success")
            results = response.json().get("results", [])
            formatted = []
            for idx, r in enumerate(results, start=1):
                formatted.append({
                    "rank": idx,
                    "similarity": 0.85 - (idx * 0.05), # mock similarity gradient
                    "chunk_text": r.get("content", ""),
                    "header": r.get("title", "Web Result"),
                    "page_no": 1,
                    "source": r.get("url", ""),
                    "document_id": 0, # 0 indicates online search result
                    "filename": r.get("title", "Web page")
                })
            return formatted
        elif response.status_code == 429:
            api_logger.warning(f"Tavily Web Search API Rate Limit Hit! Status 429: {response.text}")
            print(f"[Web Search] Tavily API returned rate limit status 429: {response.text}")
        else:
            api_logger.error(f"Tavily Web Search API Call Failed with status {response.status_code}: {response.text}")
            print(f"[Web Search] Tavily API returned status {response.status_code}: {response.text}")
    except Exception as e:
        api_logger.error(f"Tavily Web Search API Call Exception: {e}")
        print(f"[Web Search] Error during Tavily request: {e}")

    return []
