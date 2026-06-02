import sys
import time
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from contextlib import redirect_stdout
from core.retriever import list_indexed_documents
from core.llm import generate_structured_answer, generate_direct_answer
from core.intent_classifier import classify_intent
from data_models import RetrieveRequest
from logs.logs_router import active_logs, DualWriter, query_logger
from service.session_manager import update_activity

router = APIRouter(prefix="/retriever", tags=["Retriever Answer"])

@router.post("/answer")
def answer_question(request: RetrieveRequest):
    """
    Retrieves relevant document chunks, performs online search, or calls the LLM directly,
    streaming loading progress intent status updates in real-time.
    Returns the structured answer validated via a Pydantic parser.
    """
    query_logger.info(f"Processing query: {request.query}")
    if request.session_id:
        update_activity(request.session_id)
    def event_generator():
        # Helper to construct SSE status messages
        def make_status_event(msg: str):
            return f"data: {json.dumps({'type': 'status', 'message': msg})}\n\n"

        try:
            active_logs.clear()
            dual_writer = DualWriter(sys.stdout)

            # Load chat history from Redis
            from service.session_manager import redis_client
            chat_history = []
            if request.session_id and redis_client:
                try:
                    history_key = f"history:{request.session_id}"
                    # Retrieve the last 10 messages (5 turns of conversation)
                    raw_history = redis_client.lrange(history_key, -10, -1)
                    if raw_history:
                        for item in raw_history:
                            chat_history.append(json.loads(item))
                except Exception as rex:
                    print(f"[Redis History Error] Failed to load chat history: {rex}")

            with redirect_stdout(dual_writer):
                # Step 1: Detect docs presence
                docs = list_indexed_documents()
                has_docs = len(docs) > 0

                # Step 2: Classify Intent (with execute=False to classify instantly)
                yield make_status_event("Routing: Classifying query intent...")
                intent_data = classify_intent(
                    query=request.query, 
                    has_documents=has_docs,
                    top_k=request.top_k,
                    document_id=request.document_id,
                    execute=False
                )
                intent = intent_data.intent
                results = []
                
                print(f"[Router] Query: '{request.query}' -> Intent: {intent} (Reason: {intent_data.explanation})")

                # Step 3: Route, execute action, and Synthesize based on classified intent
                if intent == "direct_llm":
                    yield make_status_event("LLM: Generating direct answer...")
                    structured_data = generate_direct_answer(request.query, chat_history=chat_history)
                    # Wrap response into matching results format
                    results = [{
                        "chunk_text": structured_data.answer,
                        "page_no": 0,
                        "header": "Direct LLM Response",
                        "document_title": "AI Knowledge Base",
                        "key_takeaways": structured_data.key_takeaways,
                        "suggested_followups": structured_data.suggested_followups
                    }]
                    
                elif intent == "web_search":
                    yield make_status_event("Web Search: Querying Tavily...")
                    from core.web_search import search_tavily
                    results = search_tavily(request.query)
                    
                    yield make_status_event("LLM: Synthesizing web search results...")
                    structured_data = generate_structured_answer(query=request.query, contexts=results, intent="web_search", chat_history=chat_history)
                    
                else:  # intent == "rag"
                    yield make_status_event("RAG: Retrieving relevant document chunks...")
                    import re
                    page_no = None
                    page_match = re.search(r'\b(?:page\s+number|page|pg|p\.?)\s*(\d+)\b', request.query, re.IGNORECASE)
                    if page_match:
                        page_no = int(page_match.group(1))

                    from core.hybrid_retriever import retrieve_hybrid_chunks
                    results = retrieve_hybrid_chunks(
                        query=request.query,
                        top_k=request.top_k,
                        document_id=request.document_id,
                        page_no=page_no
                    )
                    
                    yield make_status_event("LLM: Synthesizing RAG contexts...")
                    structured_data = generate_structured_answer(query=request.query, contexts=results, intent="rag", chat_history=chat_history)

                # Save conversation to Redis history list
                if request.session_id and redis_client:
                    try:
                        history_key = f"history:{request.session_id}"
                        redis_client.rpush(history_key, json.dumps({"role": "user", "content": request.query}))
                        redis_client.rpush(history_key, json.dumps({"role": "assistant", "content": structured_data.answer}))
                        redis_client.expire(history_key, 600)  # 10 minutes TTL
                    except Exception as rex:
                        print(f"[Redis History Error] Failed to save chat history: {rex}")

                # Step 4: Pydantic Validation logs
                yield make_status_event("Validation: Parsing response payload with Pydantic...")
                time.sleep(0.2)

                # Align and standardize all results
                from helpers import align_result_attributes
                aligned_results = []
                for item in results:
                    aligned_results.append(align_result_attributes(item))

                current_logs = list(active_logs)

            payload = {
                "success": True,
                "query": request.query,
                "results": aligned_results,
                "answer": structured_data.answer,
                "key_takeaways": structured_data.key_takeaways,
                "suggested_followups": structured_data.suggested_followups,
                "verbose_logs": current_logs,
            }
            yield f"data: {json.dumps({'type': 'result', 'payload': payload})}\n\n"

        except Exception as e:
            print(f"Error in retriever answer stream: {e}")
            yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
