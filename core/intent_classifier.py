"""
core/intent_classifier.py
-------------------------
Classifies user queries using a template-driven Cohere Router.
Loads routing instructions dynamically using pathlib.
Validated and parsed via Pydantic.
"""

import os
import json
import re
from typing import Literal, List, Dict, Any, Optional
from pydantic import BaseModel, Field
import groq
from logs.logs_router import api_logger
from dotenv import load_dotenv
from helpers.prompt_loader import load_template
from sqlalchemy.orm import Session

load_dotenv()



class IntentClassification(BaseModel):
    intent: Literal["direct_llm", "rag", "web_search"] = Field(
        ...,
        description="The routing target: direct_llm, rag, or web_search."
    )
    explanation: str = Field(
        ...,
        description="Brief explanation of why this intent was selected."
    )
    results: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Optional list of retrieved chunks or LLM response generated."
    )


def classify_intent(
    query: str,
    has_documents: bool = True,
    top_k: int = 5,
    alpha: float = 0.5,
    pool_size: int = 20,
    document_id: Optional[int] = None,
    execute: bool = True,
    session_id: Optional[str] = None,
    db: Optional[Session] = None
) -> IntentClassification:
    """
    Classifies user queries using a template-loaded prompt template and dynamically resolved LLM provider.
    Triggers appropriate backend logic (RAG hybrid search, Web search, or Direct LLM) inside the intent router.
    """
    from core.llm import get_llm_client, call_llm_chat_with_retry, KeyNotFoundError
    
    # Load the requested template dynamically
    system_prompt = load_template("router_prompt.txt")

    if not has_documents:
        system_prompt += "\n\nCRITICAL OVERRIDE: Currently, there are NO documents uploaded (has_documents is False). You MUST NOT route this query to RAG. Downgrade any RAG route to LLM or WEB."

    try:
        # Resolve active client
        provider, client = get_llm_client(session_id, db)
    except KeyNotFoundError as knf:
        fallback_intent = "direct_llm" if not has_documents else "rag"
        logger = logging.getLogger("intent_classifier")
        logger.warning(f"Key missing for intent classifier: {knf}. Defaulting to fallback intent '{fallback_intent}'.")
        return IntentClassification(
            intent=fallback_intent,
            explanation=f"Default fallback triggered: LLM credentials not configured ({knf})",
            results=None
        )

    try:
        model = "llama-3.1-8b-instant" if provider == "groq" else "command-r-plus"
        api_logger.info(f"Initiating {provider.upper()} Intent Classification API Call - Model: {model}")
        
        response_content = call_llm_chat_with_retry(
            provider=provider,
            client=client,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Query: {query}"}
            ],
            response_format={"type": "json_object"},
            temperature=0.0
        )
        
        api_logger.info(f"{provider.upper()} Intent Classification API Call Success")
        parsed = json.loads(response_content)
        
        # Extract fields matching templates schema
        route = parsed.get("route", "LLM").upper()
        reason = parsed.get("reason", "")

        # Map to original intent strings
        if route == "RAG":
            intent = "rag"
        elif route == "WEB":
            intent = "web_search"
        else:
            intent = "direct_llm"

        # Execute appropriate backend search/generation
        hybrid_results = None
        
        if execute:
            if intent == "rag":
                # Auto-extract page number from query
                page_no = None
                page_match = re.search(r'\b(?:page\s+number|page|pg|p\.?)\s*(\d+)\b', query, re.IGNORECASE)
                if page_match:
                    page_no = int(page_match.group(1))
                    print(f"[Intent Classifier] Auto-detected page filter: {page_no}")

                # Auto-extract top_k from query if specified
                top_k_match = re.search(r'\btop[- ]*(?:k\s*=\s*)?(\d+)\b', query, re.IGNORECASE)
                if top_k_match:
                    top_k = int(top_k_match.group(1))
                    print(f"[Intent Classifier] Auto-detected top_k filter: {top_k}")

                from core.hybrid_retriever import retrieve_hybrid_chunks
                print(f"[Intent Classifier] RAG intent detected. Executing hybrid search for: '{query}'")
                hybrid_results = retrieve_hybrid_chunks(
                    query=query, 
                    top_k=top_k, 
                    alpha=alpha, 
                    pool_size=pool_size,
                    document_id=document_id,
                    page_no=page_no
                )
                print(f"[Intent Classifier] Hybrid search executed. Retrieved {len(hybrid_results)} chunks.")

            elif intent == "web_search":
                from core.web_search import search_tavily
                print(f"[Intent Classifier] WEB_SEARCH intent detected. Executing web search for: '{query}'")
                hybrid_results = search_tavily(query)
                print(f"[Intent Classifier] Web search executed. Retrieved {len(hybrid_results)} results.")

            elif intent == "direct_llm":
                from core.llm import generate_direct_answer
                print(f"[Intent Classifier] DIRECT_LLM intent detected. Generating direct LLM response...")
                direct_ans = generate_direct_answer(query, session_id=session_id, db=db)
                # Wrap response into matching results format
                hybrid_results = [{
                    "chunk_text": direct_ans.answer,
                    "page_no": 0,
                    "header": "Direct LLM Response",
                    "document_title": "AI Knowledge Base",
                    "key_takeaways": direct_ans.key_takeaways,
                    "suggested_followups": direct_ans.suggested_followups
                }]
                print(f"[Intent Classifier] Direct LLM response generated successfully.")

        return IntentClassification(
            intent=intent,
            explanation=reason,
            results=hybrid_results
        )
    except Exception as e:
        api_logger.error(f"Error during intent classification: {e}")
        print(f"Error during intent classification: {e}")
        # Default fallback
        fallback_intent = "direct_llm" if not has_documents else "rag"
        
        # Fallback handling
        hybrid_results = None
        if execute:
            try:
                if fallback_intent == "rag":
                    page_no = None
                    page_match = re.search(r'\b(?:page\s+number|page|pg|p\.?)\s*(\d+)\b', query, re.IGNORECASE)
                    if page_match:
                        page_no = int(page_match.group(1))

                    top_k_match = re.search(r'\btop[- ]*(?:k\s*=\s*)?(\d+)\b', query, re.IGNORECASE)
                    if top_k_match:
                        top_k = int(top_k_match.group(1))

                    from core.hybrid_retriever import retrieve_hybrid_chunks
                    print(f"[Intent Classifier Fallback] RAG fallback. Executing hybrid search for: '{query}'")
                    hybrid_results = retrieve_hybrid_chunks(
                        query=query, 
                        top_k=top_k, 
                        alpha=alpha, 
                        pool_size=pool_size,
                        document_id=document_id,
                        page_no=page_no
                    )
                elif fallback_intent == "web_search":
                    from core.web_search import search_tavily
                    print(f"[Intent Classifier Fallback] WEB fallback. Executing web search for: '{query}'")
                    hybrid_results = search_tavily(query)
                elif fallback_intent == "direct_llm":
                    from core.llm import generate_direct_answer
                    print(f"[Intent Classifier Fallback] LLM fallback. Generating direct response...")
                    direct_ans = generate_direct_answer(query, session_id=session_id, db=db)
                    hybrid_results = [{
                        "chunk_text": direct_ans.answer,
                        "page_no": 0,
                        "header": "Direct LLM Response (Fallback)",
                        "document_title": "AI Knowledge Base",
                        "key_takeaways": direct_ans.key_takeaways,
                        "suggested_followups": direct_ans.suggested_followups
                    }]
            except Exception as ex:
                print(f"[Intent Classifier Fallback] Execution failed: {ex}")

        return IntentClassification(
            intent=fallback_intent,
            explanation=f"Fallback triggered due to error: {e}",
            results=hybrid_results
        )

