"""
core/llm.py
------------
Interface to Groq Chat Completions API for RAG synthesis.
"""

import os
from typing import List, Dict, Any, Generator, Optional, Tuple
from groq import Groq
import groq
import cohere
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from data_models import StructuredAnswer
from logs.logs_router import api_logger
from sqlalchemy.orm import Session

# Load environment if present (for local developer override)
load_dotenv()

# Build the tuple of rate-limit exceptions for retry logic
RATE_LIMIT_EXCEPTIONS = (groq.RateLimitError,)
try:
    import cohere.errors
    RATE_LIMIT_EXCEPTIONS += (cohere.errors.TooManyRequestsError,)
except Exception:
    pass

from service.byok_service import provider_manager, KeyNotFoundError
from core.database import SessionLocal

def get_llm_client(session_id: Optional[str] = None, db: Optional[Session] = None) -> Tuple[str, Any]:
    """
    Dynamically retrieves the active LLM client (Groq or Cohere) for the session/user.
    If no user-specific key is configured, falls back to environment variables.
    Raises KeyNotFoundError if no credentials can be resolved.
    """
    opened_db = False
    if db is None:
        db = SessionLocal()
        opened_db = True
        
    try:
        if session_id:
            try:
                provider, client = provider_manager.get_active_client(db, session_id)
                return provider, client
            except KeyNotFoundError:
                pass
                
        # Fallback to environment variables
        groq_env = os.getenv("GROQ_API_KEY")
        if groq_env:
            active_provider = "groq"
            if session_id:
                try:
                    active_provider = provider_manager.get_active_provider(db, session_id)
                except Exception:
                    pass
            if active_provider == "cohere" and os.getenv("COHERE_API_KEY"):
                return "cohere", cohere.Client(api_key=os.getenv("COHERE_API_KEY"))
            return "groq", Groq(api_key=groq_env)
            
        cohere_env = os.getenv("COHERE_API_KEY")
        if cohere_env:
            return "cohere", cohere.Client(api_key=cohere_env)
            
        raise KeyNotFoundError("No LLM API keys configured. Please upload an API key.")
    finally:
        if opened_db:
            db.close()


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(RATE_LIMIT_EXCEPTIONS),
    reraise=True
)
def call_llm_chat_with_retry(
    provider: str,
    client: Any,
    messages: List[Dict[str, str]],
    response_format: Optional[Dict[str, Any]] = None,
    temperature: float = 0.2,
    max_tokens: int = 1024
) -> str:
    """
    Wrapper for LLM completions with automatic tenacity-based retries.
    Supports both Groq and Cohere clients dynamically.
    """
    model = "llama-3.1-8b-instant" if provider == "groq" else "command-r-plus"
    try:
        api_logger.info(f"Initiating {provider.upper()} Chat Completion - Model: {model}")
        
        if provider == "groq":
            kwargs = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            if response_format:
                kwargs["response_format"] = response_format
            res = client.chat.completions.create(**kwargs)
            result_text = res.choices[0].message.content
        elif provider == "cohere":
            # Extract system prompt, message, and history for Cohere structure
            system_prompt = ""
            user_message = ""
            cohere_history = []
            
            for msg in messages:
                role = msg.get("role", "").lower()
                content = msg.get("content", "")
                if role == "system":
                    system_prompt = content
                elif role == "user":
                    if msg == messages[-1]:
                        user_message = content
                    else:
                        cohere_history.append({"role": "USER", "message": content})
                elif role in ("assistant", "chatbot"):
                    cohere_history.append({"role": "CHATBOT", "message": content})
            
            if not user_message and messages:
                user_message = messages[-1].get("content", "")
                
            kwargs = {
                "model": model,
                "message": user_message,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            if system_prompt:
                kwargs["preamble"] = system_prompt
            if cohere_history:
                kwargs["chat_history"] = cohere_history
            if response_format:
                kwargs["response_format"] = response_format
                
            res = client.chat(**kwargs)
            result_text = res.text
        else:
            raise ValueError(f"Unknown provider: {provider}")
            
        api_logger.info(f"{provider.upper()} Chat Completion API Call Success")
        return result_text
    except RATE_LIMIT_EXCEPTIONS as rle:
        api_logger.warning(f"{provider.upper()} API Rate Limit Hit! Detail: {rle}")
        raise
    except Exception as e:
        api_logger.error(f"{provider.upper()} API Call Failed: {e}")
        raise



def generate_rag_stream(
    query: str,
    contexts: List[Dict[str, Any]],
    session_id: Optional[str] = None,
    db: Optional[Session] = None
) -> Generator[str, None, None]:
    """
    Generate a streamed answer synthesized from the retrieved contexts.
    Dynamically loads the client (Groq or Cohere) based on active provider configuration.
    """
    # Construct context block
    context_str = ""
    for idx, c in enumerate(contexts, start=1):
        filename = c.get("filename", "Unknown file")
        page_no = c.get("page_no", "?")
        text = c.get("chunk_text", "")
        context_str += f"[{idx}] Source: {filename} (Page {page_no})\nContent: {text}\n\n"

    try:
        from helpers.prompt_loader import load_template
        template = load_template("rag_template.txt")
        system_prompt = template.format(rag_context=context_str, user_query=query)
    except Exception as e:
        print(f"Error loading rag_template.txt for streaming: {e}")
        system_prompt = (
            "You are HybridCache RAG v2's Assistant, an advanced AI designed to answer questions accurately "
            "using only the provided context retrieved from PDF documents.\n\n"
            "Instructions:\n"
            "1. Answer the question detail-by-detail, citing the sources in brackets (e.g. [1], [2]) "
            "whenever you use information from them.\n"
            "2. Keep your answers clear, professional, and well-structured. You can use markdown (bullet points, bold text).\n"
            "3. If the context does not contain enough information to answer the question, state politely "
            "that the context does not specify, but summarize any partial clues if present.\n"
            "4. Rely ONLY on the facts mentioned in the context. Do not make up or assume information."
        )

    user_content = f"CONTEXTS:\n{context_str}\n\nQUESTION: {query}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

    try:
        provider, client = get_llm_client(session_id, db)
    except KeyNotFoundError as knf:
        yield f"\n[API Key configuration missing: {knf}]"
        return

    try:
        if provider == "groq":
            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                stream=True,
                temperature=0.2,
                max_tokens=1024,
            )
            for chunk in completion:
                token = chunk.choices[0].delta.content
                if token:
                    yield token
        elif provider == "cohere":
            # Extract preamble, message, and history for Cohere streaming
            system_prompt_co = ""
            user_message_co = ""
            cohere_history = []
            
            for msg in messages:
                role = msg.get("role", "").lower()
                content = msg.get("content", "")
                if role == "system":
                    system_prompt_co = content
                elif role == "user":
                    if msg == messages[-1]:
                        user_message_co = content
                    else:
                        cohere_history.append({"role": "USER", "message": content})
            
            if not user_message_co and messages:
                user_message_co = messages[-1].get("content", "")
                
            kwargs = {
                "model": "command-r-plus",
                "message": user_message_co,
                "temperature": 0.2,
                "max_tokens": 1024
            }
            if system_prompt_co:
                kwargs["preamble"] = system_prompt_co
            if cohere_history:
                kwargs["chat_history"] = cohere_history
                
            for event in client.chat_stream(**kwargs):
                if event.event_type == "text-generation":
                    yield event.text
    except Exception as e:
        print(f"Error during {provider} generation: {e}")
        yield f"\n[Error generating answer: {e}]"



def generate_structured_answer(
    query: str,
    contexts: List[Dict[str, Any]],
    intent: str = "rag",
    chat_history: Optional[List[Dict[str, str]]] = None,
    session_id: Optional[str] = None,
    db: Optional[Session] = None
) -> StructuredAnswer:
    """
    Generate a structured answer synthesized from the retrieved contexts.
    Uses dynamic LLM resolution (Groq or Cohere) and enforces JSON schema parsing.
    """
    import os
    from core.database import SessionLocal
    from schemas.table_schema import TableData

    context_str = ""
    injected_table_pages: set = set()

    for idx, c in enumerate(contexts, start=1):
        filename = c.get("filename", "Unknown file")
        page_no  = c.get("page_no", "?")
        text     = c.get("chunk_text", "")
        doc_id   = c.get("document_id")
        context_str += f"[{idx}] Source: {filename} (Page {page_no})\nContent: {text}\n\n"

        # Inject table markdown content for this page if not already done
        if c.get("has_tables") and doc_id and page_no and (doc_id, page_no) not in injected_table_pages:
            injected_table_pages.add((doc_id, page_no))
            
            # Reuse passed db session or open a new one
            opened_db = False
            db_session = db
            if db_session is None:
                db_session = SessionLocal()
                opened_db = True
                
            try:
                tbl_rows = db_session.query(TableData).filter(
                    TableData.document_id == doc_id,
                    TableData.page_no == page_no
                ).all()
                for tbl in tbl_rows:
                    tbl_path = tbl.table_path
                    if tbl_path and not os.path.isabs(tbl_path):
                        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        tbl_path = os.path.join(base_dir, tbl_path)
                    if tbl_path and os.path.exists(tbl_path):
                        with open(tbl_path, encoding="utf-8") as f:
                            tbl_md = f.read().strip()
                        tbl_header = tbl.header.lstrip('#').strip() if tbl.header else "Table"
                        context_str += (
                            f"Table on Page {page_no} (Section: {tbl_header}):\n"
                            f"{tbl_md}\n\n"
                        )
            except Exception as tbl_err:
                print(f"[LLM] Table injection warning: {tbl_err}")
            finally:
                if opened_db:
                    db_session.close()

    import json
    import re
    schema = StructuredAnswer.model_json_schema()
    schema_str = json.dumps(schema, indent=2)

    try:
        from helpers.prompt_loader import load_template
        if intent == "web_search":
            template = load_template("web_scrap.txt")
            web_results_str = ""
            for idx, r in enumerate(contexts, start=1):
                title = r.get("filename") or r.get("header") or "Web Page"
                url = r.get("source") or "No link"
                content = r.get("chunk_text") or ""
                web_results_str += f"[{idx}] Title: {title}\nURL: {url}\nContent: {content}\n\n"
            base_prompt = template.format(web_results=web_results_str, user_query=query)
            base_prompt_clean = re.sub(r'## Response Format.*?(?=## Quality Requirements|#|$)', '', base_prompt, flags=re.DOTALL)
        elif intent == "direct_llm":
            template = load_template("llm_template.txt")
            base_prompt = template
            base_prompt_clean = re.sub(r'## Markdown Formatting.*?(?=## Response Adaptation|#|$)', '', base_prompt, flags=re.DOTALL)
        else: # rag
            template = load_template("rag_template.txt")
            base_prompt = template.format(rag_context=context_str, user_query=query)
            base_prompt_clean = re.sub(r'# RESPONSE GUIDELINES.*', '', base_prompt, flags=re.DOTALL)
    except Exception as e:
        print(f"Error loading template for intent {intent}: {e}. Falling back to default.")
        base_prompt_clean = (
            "You are HybridCache RAG v2's Assistant, an advanced AI designed to answer questions accurately "
            "using only the provided context retrieved from PDF documents."
        )

    system_prompt = (
        f"{base_prompt_clean}\n\n"
        "You must respond with a JSON object that strictly adheres to this JSON schema:\n"
        f"{schema_str}\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. Output ONLY a raw JSON object. Do NOT wrap the response in markdown code blocks (such as ```json). The output must start with '{' and end with '}'.\n"
        "2. Do NOT add any notes, conversational text, or explanations before or after the JSON block.\n"
        "3. Ensure the JSON is well-formed and matches the schema keys exactly ('answer', 'key_takeaways', 'suggested_followups').\n"
        "4. Keep explanations concise and relevant.\n"
        "5. For any tabular data, points tables, standings, statistical lists, or matrices, you MUST format the 'answer' text using standard Markdown pipe-table syntax (e.g., | Header 1 | Header 2 | followed by |---|---| on the next line). Do NOT output tabular data as lists, plain text, or preformatted text blocks."
    )

    user_content = f"CONTEXTS:\n{context_str}\n\nQUESTION: {query}" if intent != "direct_llm" else query

    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        messages.extend(chat_history)
    messages.append({"role": "user", "content": user_content})

    try:
        provider, client = get_llm_client(session_id, db)
    except KeyNotFoundError as knf:
        return StructuredAnswer(
            answer=f"Unable to generate answer: {knf}",
            key_takeaways=["LLM API Key missing"],
            suggested_followups=["Please navigate to BYOK settings to configure your API key"]
        )

    # Try 1: with response_format={"type": "json_object"}
    try:
        raw_response = call_llm_chat_with_retry(
            provider=provider,
            client=client,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.2,
            max_tokens=1024,
        )
        return StructuredAnswer.model_validate_json(raw_response)
    except Exception as e:
        print(f"{provider.upper()} JSON mode failed for structured generation: {e}. Retrying without JSON mode constraint...")
        
        # Try 2: Fallback without response_format and clean up markdown blocks in python
        try:
            raw_response = call_llm_chat_with_retry(
                provider=provider,
                client=client,
                messages=messages,
                temperature=0.2,
                max_tokens=1024,
            )
            
            cleaned_json = raw_response.strip()
            if cleaned_json.startswith("```"):
                first_newline = cleaned_json.find("\n")
                if first_newline != -1:
                    cleaned_json = cleaned_json[first_newline:].strip()
                if cleaned_json.endswith("```"):
                    cleaned_json = cleaned_json[:-3].strip()
            
            start = cleaned_json.find("{")
            end = cleaned_json.rfind("}")
            if start != -1 and end != -1:
                cleaned_json = cleaned_json[start:end+1]
                
            return StructuredAnswer.model_validate_json(cleaned_json)
        except Exception as retry_e:
            print(f"Fallback structured generation failed: {retry_e}")
            return StructuredAnswer(
                answer=f"An error occurred while generating the structured answer: {e}",
                key_takeaways=["Error occurred during generation"],
                suggested_followups=["Try submitting your query again"]
            )


def generate_direct_answer(
    query: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    session_id: Optional[str] = None,
    db: Optional[Session] = None
) -> StructuredAnswer:
    """
    Generate a general, direct answer to the query without retrieved contexts.
    Uses dynamic LLM resolution (Groq or Cohere) and enforces JSON schema parsing.
    """
    import json
    import re
    schema = StructuredAnswer.model_json_schema()
    schema_str = json.dumps(schema, indent=2)

    try:
        from helpers.prompt_loader import load_template
        base_prompt = load_template("llm_template.txt")
    except Exception as e:
        print(f"Error loading llm_template.txt: {e}. Falling back to default.")
        base_prompt = "You are HybridCache RAG v2's Assistant, an advanced AI designed to answer questions accurately."

    base_prompt_clean = re.sub(r'## Markdown Formatting.*?(?=## Response Adaptation|#|$)', '', base_prompt, flags=re.DOTALL)

    system_prompt = (
        f"{base_prompt_clean}\n\n"
        "You must respond with a JSON object that strictly adheres to this JSON schema:\n"
        f"{schema_str}\n\n"
        "CRITICAL INSTRUCTIONS:\n"
        "1. Output ONLY a raw JSON object. Do NOT wrap the response in markdown code blocks (such as ```json). The output must start with '{' and end with '}'.\n"
        "2. Do NOT add any notes, conversational text, or explanations before or after the JSON block.\n"
        "3. Ensure the JSON is well-formed and matches the schema keys exactly ('answer', 'key_takeaways', 'suggested_followups').\n"
        "4. Provide a helpful, clear, and comprehensive answer to the user's question.\n"
        "5. Do not include or make up fake document citations since you are answering from general knowledge."
    )

    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        messages.extend(chat_history)
    messages.append({"role": "user", "content": query})

    try:
        provider, client = get_llm_client(session_id, db)
    except KeyNotFoundError as knf:
        return StructuredAnswer(
            answer=f"Unable to generate answer: {knf}",
            key_takeaways=["LLM API Key missing"],
            suggested_followups=["Please navigate to BYOK settings to configure your API key"]
        )

    # Try 1: with response_format={"type": "json_object"}
    try:
        raw_response = call_llm_chat_with_retry(
            provider=provider,
            client=client,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.4,
            max_tokens=1024,
        )
        return StructuredAnswer.model_validate_json(raw_response)
    except Exception as e:
        print(f"{provider.upper()} JSON mode failed for direct structured generation: {e}. Retrying without JSON mode constraint...")
        
        # Try 2: Fallback without response_format and clean up markdown blocks in python
        try:
            raw_response = call_llm_chat_with_retry(
                provider=provider,
                client=client,
                messages=messages,
                temperature=0.4,
                max_tokens=1024,
            )
            
            cleaned_json = raw_response.strip()
            if cleaned_json.startswith("```"):
                first_newline = cleaned_json.find("\n")
                if first_newline != -1:
                    cleaned_json = cleaned_json[first_newline:].strip()
                if cleaned_json.endswith("```"):
                    cleaned_json = cleaned_json[:-3].strip()
            
            start = cleaned_json.find("{")
            end = cleaned_json.rfind("}")
            if start != -1 and end != -1:
                cleaned_json = cleaned_json[start:end+1]
                
            return StructuredAnswer.model_validate_json(cleaned_json)
        except Exception as retry_e:
            print(f"Fallback direct structured generation failed: {retry_e}")
            return StructuredAnswer(
                answer=f"An error occurred while generating the direct answer: {e}",
                key_takeaways=["Error occurred during direct generation"],
                suggested_followups=["Try submitting your query again"]
            )



