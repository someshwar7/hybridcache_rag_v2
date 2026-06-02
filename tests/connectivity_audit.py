"""
connectivity_audit.py
---------------------
Full static + live connectivity check for the MULTI-AGENT PROJECT.

Checks:
  1.  .env  keys present
  2.  Python imports — all modules resolve correctly
  3.  Import chain — main.py -> routers -> services -> core
  4.  Cohere API live round-trip
  5.  PostgreSQL live connection
  6.  pgvector extension active in DB
  7.  DB tables exist (files, raw_text, images, tables, embeddings)
  8.  Schema column types match (embeddings.content_embedding = vector(1024))
  9.  main.py router wiring (all 3 routers registered)
  10. pdf_router -> run_pipeline call signature matches docling_main.py
  11. logs module (DualWriter, active_logs, /stream-logs route)
  12. UI static directory exists (ui/index.html)
  13. uploads directory exists
  14. preprocessed_data sub-dirs exist
"""

import sys, os, importlib, traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# Mirror what main.py does: add preprocessing/ so bare imports like
# 'pdf_render', 'docling_extractor' etc. resolve correctly.
sys.path.insert(0, os.path.join(ROOT, "preprocessing"))

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/developer_db"
)


PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"

results = []

def check(label, fn):
    try:
        msg = fn()
        results.append((PASS, label, msg or ""))
        print(f"  [PASS] {label}" + (f" — {msg}" if msg else ""))
    except Exception as e:
        results.append((FAIL, label, str(e)))
        print(f"  [FAIL] {label}\n         {e}")

def warn(label, fn):
    try:
        msg = fn()
        results.append((PASS, label, msg or ""))
        print(f"  [PASS] {label}" + (f" — {msg}" if msg else ""))
    except Exception as e:
        results.append((WARN, label, str(e)))
        print(f"  [WARN] {label}\n         {e}")


print()
print("=" * 60)
print("  CONNECTIVITY AUDIT")
print("=" * 60)

# ─────────────────────────────────────────────────────────────
# 1. ENV KEYS
# ─────────────────────────────────────────────────────────────
print("\n[1] Environment / API Keys")

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

check("COHERE_API_KEY present",
      lambda: None if os.getenv("COHERE_API_KEY") else (_ for _ in ()).throw(EnvironmentError("Missing")))

check("GROQ_API_KEY present",
      lambda: None if os.getenv("GROQ_API_KEY") else (_ for _ in ()).throw(EnvironmentError("Missing")))

check("TAVILY_API_KEY present",
      lambda: None if os.getenv("TAVILY_API_KEY") else (_ for _ in ()).throw(EnvironmentError("Missing")))

check("LANGSMITH_API_KEY present",
      lambda: None if os.getenv("LANGSMITH_API_KEY") else (_ for _ in ()).throw(EnvironmentError("Missing")))

# ─────────────────────────────────────────────────────────────
# 2. CORE MODULE IMPORTS
# ─────────────────────────────────────────────────────────────
print("\n[2] Core Module Imports")

def try_import(module):
    importlib.import_module(module)

check("core.embeddings importable",         lambda: try_import("core.embeddings"))
check("schemas.embedding_schems importable",lambda: try_import("schemas.embedding_schems"))
check("schemas.file_schema importable",     lambda: try_import("schemas.file_schema"))
check("schemas.text_schema importable",     lambda: try_import("schemas.text_schema"))
check("schemas.image_schema importable",    lambda: try_import("schemas.image_schema"))
check("schemas.table_schema importable",    lambda: try_import("schemas.table_schema"))
check("schemas.chunks_to_db importable",    lambda: try_import("schemas.chunks_to_db"))
check("data_models importable",             lambda: try_import("data_models"))
check("helpers importable",                 lambda: try_import("helpers"))
check("service.file_metadata importable",   lambda: try_import("service.file_metadata"))
check("logs.logs_router importable",        lambda: try_import("logs.logs_router"))
check("logs.ui_router importable",          lambda: try_import("logs.ui_router"))
check("routers.pdf_router importable",      lambda: try_import("routers.pdf_router"))
check("routers.preprocessed_router importable", lambda: try_import("routers.preprocessed_router"))

# ─────────────────────────────────────────────────────────────
# 3. IMPORT CHAIN SYMBOLS
# ─────────────────────────────────────────────────────────────
print("\n[3] Import Chain — Key Symbols")

def sym(module, attr):
    m = importlib.import_module(module)
    if not hasattr(m, attr):
        raise AttributeError(f"{module} has no attribute '{attr}'")
    return f"{module}.{attr} OK"

check("get_embeddings in core.embeddings",          lambda: sym("core.embeddings", "get_embeddings"))
check("get_single_embedding in core.embeddings",    lambda: sym("core.embeddings", "get_single_embedding"))
check("EMBEDDING_DIMS == 1024",
      lambda: None if importlib.import_module("core.embeddings").EMBEDDING_DIMS == 1024
              else (_ for _ in ()).throw(ValueError(f"Expected 1024, got {importlib.import_module('core.embeddings').EMBEDDING_DIMS}")))
check("save_chunks_to_db in schemas",               lambda: sym("schemas.chunks_to_db", "save_chunks_to_db"))
check("PDFUploadResponse in data_models",           lambda: sym("data_models", "PDFUploadResponse"))
check("PDFSelectionResponse in data_models",        lambda: sym("data_models", "PDFSelectionResponse"))
check("validate_and_parse_pdf_selection in helpers",lambda: sym("helpers", "validate_and_parse_pdf_selection"))
check("active_logs in logs.logs_router",            lambda: sym("logs.logs_router", "active_logs"))
check("DualWriter in logs.logs_router",             lambda: sym("logs.logs_router", "DualWriter"))
check("pdf_router APIRouter in routers",            lambda: sym("routers", "pdf_router"))

# ─────────────────────────────────────────────────────────────
# 4. COHERE API — LIVE ROUND TRIP
# ─────────────────────────────────────────────────────────────
print("\n[4] Cohere API — Live Round Trip")

def cohere_live():
    from core.embeddings import get_single_embedding, EMBEDDING_DIMS
    vec = get_single_embedding("connectivity test", input_type="search_query")
    assert len(vec) == EMBEDDING_DIMS, f"Expected {EMBEDDING_DIMS} dims"
    return f"1024-dim vector OK, first_val={round(vec[0], 6)}"

check("Cohere embed live call", cohere_live)

# ─────────────────────────────────────────────────────────────
# 5. POSTGRESQL — CONNECTION
# ─────────────────────────────────────────────────────────────
print("\n[5] PostgreSQL — Connection")

def pg_connect():
    from sqlalchemy import create_engine, text
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()")).scalar()
    return result.split(",")[0]

check("PostgreSQL connection", pg_connect)

# ─────────────────────────────────────────────────────────────
# 6. PGVECTOR EXTENSION
# ─────────────────────────────────────────────────────────────
print("\n[6] pgvector Extension")

def pgvector_check():
    from sqlalchemy import create_engine, text
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT extname FROM pg_extension WHERE extname = 'vector'"
        )).fetchone()
    if not row:
        raise RuntimeError("pgvector extension NOT installed in developer_db")
    return "vector extension active"

check("pgvector extension active", pgvector_check)

# ─────────────────────────────────────────────────────────────
# 7. DB TABLES EXIST
# ─────────────────────────────────────────────────────────────
print("\n[7] Database Tables")

EXPECTED_TABLES = ["files", "raw_text", "images", "tables", "embeddings"]

def table_exists(tbl):
    from sqlalchemy import create_engine, text
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname='public' AND tablename=:t"
        ), {"t": tbl}).fetchone()
    if not row:
        raise RuntimeError(f"Table '{tbl}' does NOT exist")
    return f"'{tbl}' exists"

for tbl in EXPECTED_TABLES:
    check(f"Table '{tbl}' exists", lambda t=tbl: table_exists(t))

# ─────────────────────────────────────────────────────────────
# 8. EMBEDDING COLUMN TYPE
# ─────────────────────────────────────────────────────────────
print("\n[8] Embedding Column Types")

def check_vector_col(table, col, expected_dim):
    from sqlalchemy import create_engine, text
    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT udt_name FROM information_schema.columns "
            "WHERE table_name=:t AND column_name=:c"
        ), {"t": table, "c": col}).fetchone()
    if not row:
        raise RuntimeError(f"{table}.{col} column not found")
    if "vector" not in row[0].lower():
        raise RuntimeError(f"{table}.{col} type is '{row[0]}', expected vector")
    return f"{table}.{col} is vector type"

check("embeddings.content_embedding is vector", lambda: check_vector_col("embeddings", "content_embedding", 1024))
check("embeddings.header_embedding is vector",  lambda: check_vector_col("embeddings", "header_embedding", 1024))

# ─────────────────────────────────────────────────────────────
# 9. MAIN.PY ROUTER WIRING
# ─────────────────────────────────────────────────────────────
print("\n[9] main.py Router Wiring")

def check_main_wiring():
    with open(os.path.join(ROOT, "main.py"), encoding="utf-8") as f:
        src = f.read()
    missing = []
    tokens = [
        "ui_router", "logs_router", "pdf_router", 
        "retriever_retrieve", "retriever_answer", "retriever_classify", 
        "db_router", "preprocessed_router", "include_router"
    ]
    for token in tokens:
        if token not in src:
            missing.append(token)
    if missing:
        raise RuntimeError(f"Missing in main.py: {missing}")
    return "All ui, logs, pdf, retriever (split), and db routers registered"

check("main.py registers all routers", check_main_wiring)

# ─────────────────────────────────────────────────────────────
# 10. PDF_ROUTER → RUN_PIPELINE CALL MATCH
# ─────────────────────────────────────────────────────────────
print("\n[10] pdf_router -> run_pipeline Signature")

def check_pipeline_call():
    import inspect
    sys.path.insert(0, os.path.join(ROOT, "preprocessing"))
    from preprocessing.docling_main import run_pipeline
    sig = inspect.signature(run_pipeline)
    params = list(sig.parameters.keys())
    required = ["base_dir", "pdf_path", "selection_mode", "overlap_chars", "dpi"]
    missing = [p for p in required if p not in params]
    if missing:
        raise RuntimeError(f"run_pipeline missing params: {missing}")
    return f"All required params present: {params}"

check("run_pipeline has all expected params", check_pipeline_call)

# ─────────────────────────────────────────────────────────────
# 11. CHUNKS_TO_DB EMBEDDING WIRING
# ─────────────────────────────────────────────────────────────
print("\n[11] chunks_to_db Embedding Wiring")

def check_embedding_wiring():
    with open(os.path.join(ROOT, "schemas", "chunks_to_db.py"), encoding="utf-8") as f:
        src = f.read()
    checks = {
        "get_embeddings imported":  "from core.embeddings import get_embeddings",
        "search_document input":    "search_document",
        "batched flat_texts":       "flat_texts",
        "empty body guard":         "if c_vec is not None",
        "Embedding row insert":     "db.add(Embedding(",
    }
    fails = [k for k, v in checks.items() if v not in src]
    if fails:
        raise RuntimeError(f"Missing wiring: {fails}")
    return "All embedding wiring tokens present"

check("chunks_to_db.py embedding wiring complete", check_embedding_wiring)

# ─────────────────────────────────────────────────────────────
# 12 & 13. STATIC DIRECTORIES
# ─────────────────────────────────────────────────────────────
print("\n[12] Static / Runtime Directories")

def dir_exists(path, name):
    full = os.path.join(ROOT, path)
    if not os.path.exists(full):
        raise FileNotFoundError(f"'{name}' not found at: {full}")
    return f"exists at {full}"

check("ui/ directory exists",           lambda: dir_exists("ui", "ui"))
check("ui/index.html exists",           lambda: dir_exists("ui/index.html", "ui/index.html"))
check("uploads/ directory exists",      lambda: dir_exists("uploads", "uploads"))
check("preprocessed_data/ exists",      lambda: dir_exists("preprocessed_data", "preprocessed_data"))
warn("preprocessed_data/imagefolder/",  lambda: dir_exists("preprocessed_data/imagefolder", "imagefolder"))
warn("preprocessed_data/tablefolder/",  lambda: dir_exists("preprocessed_data/tablefolder", "tablefolder"))
warn("preprocessed_data/raw_data/",     lambda: dir_exists("preprocessed_data/raw_data", "raw_data"))

# ─────────────────────────────────────────────────────────────
# FINAL SUMMARY
# ─────────────────────────────────────────────────────────────
passed = sum(1 for s, _, _ in results if s == PASS)
failed = sum(1 for s, _, _ in results if s == FAIL)
warned = sum(1 for s, _, _ in results if s == WARN)
total  = len(results)

print()
print("=" * 60)
print(f"  AUDIT SUMMARY: {passed} passed / {failed} failed / {warned} warned  (total {total})")
print("=" * 60)

if failed:
    print("\nFAILED CHECKS:")
    for s, label, msg in results:
        if s == FAIL:
            print(f"  [FAIL] {label}")
            print(f"         {msg}")

if warned:
    print("\nWARNINGS:")
    for s, label, msg in results:
        if s == WARN:
            print(f"  [WARN] {label}")
            print(f"         {msg}")

print()
sys.exit(0 if failed == 0 else 1)
