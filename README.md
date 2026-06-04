# 🚀 HybridCache RAG v2

An advanced, high-performance Retrieval-Augmented Generation (RAG) assistant designed with a clean, modern dark dashboard layout and responsive side panels.

The application utilizes **Docling** for deep semantic document layout parsing, **PostgreSQL** with the `pgvector` extension for semantic storage, **Redis** for session management and file-lifecycle cache control, **Cohere** for vector embeddings and reranking, and **Groq** for rapid LLM orchestration. Web-scraped tables and markdown code-blocks are dynamically parsed and rendered as visual HTML blocks.

---

## 📸 System Workflows: V1 vs. V2

Below is a visual side-by-side comparison showcasing the progression from the legacy Traditional RAG pipeline to the optimized HybridCache RAG v2 architecture.

| Legacy: Traditional RAG v1 | Modern: HybridCache RAG v2 |
| :---: | :---: |
| ![Traditional RAG v1](arch/TRADITIONAL%20RAG%20V1.gif) | ![HybridCache RAG v2](arch/HYBRID%20CACHE%20RAG%20V2.gif) |

---

## 🖥️ User Interface Tour

Explore the main features and layout of the HybridCache RAG v2 interface using the interactive slides below (expand each section to view):

<details open>
  <summary><b>Slide 1: Interactive Upload &amp; Page Range Selector</b></summary>
  <p>The main dashboard allows users to attach documents (such as <code>book.pdf</code>) and configure custom page indexing ranges for targeted semantic extraction.</p>
  <p align="center">
    <img src="arch/ui1.png" alt="Slide 1: Upload and Page Range Selector" width="95%" />
  </p>
</details>

<details>
  <summary><b>Slide 2: Ingestion Pipeline &amp; Live Developer Logs</b></summary>
  <p>Track the multi-stage ingestion process in real-time. The Document Inspector panel shows live developer logs detailing layout scanning, frame rendering, and parsing progress.</p>
  <p align="center">
    <img src="arch/ui2.png" alt="Slide 2: Ingestion Progress and Developer Logs" width="95%" />
  </p>
</details>

<details>
  <summary><b>Slide 3: Context-Aware Chat &amp; Page Viewer</b></summary>
  <p>Interact with the ingested documents through an AI chat interface. View synthetic responses, key takeaways, and relevant source page renders side-by-side.</p>
  <p align="center">
    <img src="arch/ui3.png" alt="Slide 3: Semantic Chat and Page Viewer" width="95%" />
  </p>
</details>

<details>
  <summary><b>Slide 4: Structured Metadata &amp; JSON Inspector</b></summary>
  <p>Access structured semantic details, paragraph context text, and similarity scores returned by the Groq/Cohere orchestrator inside the interactive JSON inspector.</p>
  <p align="center">
    <img src="arch/ui4.png" alt="Slide 4: JSON Response Inspector" width="95%" />
  </p>
</details>

---

## 🛠️ Environment Configurations (`.env`)

Create a `.env` file at the root of the project. Below are the required and optional environment configurations:

```ini
# --- LLM API Credentials ---
GROQ_API_KEY="your-groq-api-key"
COHERE_API_KEY="your-cohere-api-key"
TAVILY_API_KEY="your-tavily-api-key"

# --- LangSmith Observability & Tracing (Optional) ---
LANGSMITH_API_KEY="your-langsmith-api-key"
LANGSMITH_TRACING=true

# --- Database & Caching Configurations (Defaults shown) ---
DATABASE_URL="postgresql://username:password@localhost:5432/database_name"
REDIS_HOST="localhost"
REDIS_PORT=6379
REDIS_DB=0
```

> [!NOTE]
> Make sure to create a new database on your local PostgreSQL instance (e.g., named `developer_db`) and paste its connection string in your `.env` file under the `DATABASE_URL` key.

---

## 📐 System Flow & Architecture

The application handles operations through three distinct flows:

```mermaid
graph TD
    A[User Request] --> B[Intent Classifier]
    B -->|RAG| C[Query Embedding + BM25 Keyword Search]
    B -->|Web Search| D[Tavily Search API Query]
    B -->|Direct LLM| E[Direct Groq Inference]
    
    C --> F[Cohere Reranking Engine]
    F --> G[Extract Context from PostgreSQL]
    G --> H[Groq Structured Response Synthesis]
    D --> H
    E --> H
    
    H --> I[Frontend UI Parser]
    I -->|Tabular standings / code blocks| J[Styled HTML visual rendering]
```

### A. Document Upload & Preprocessing Flow
1. **Upload**: User uploads a PDF file.
2. **Page Rendering**: `PyMuPDF` (`fitz`) and `Pillow` (`PIL`) render document page frames as base64 images for visual inspection.
3. **Semantic Extraction**: The **Docling** engine runs layout-segmentation and OCR models (utilizing local **PyTorch** dependencies) to extract paragraphs, headers, and tables.
4. **Embedding**: Cohere API embeds the text chunks into vectors.
5. **Persistence**: Chunks, metadata, page associations, and embeddings are committed to the PostgreSQL `developer_db` schema. Unfinished or timed-out session uploads are managed by Redis cache expirations.

### B. Query & Retrieval Flow
1. **Classification**: `groq` classifies the query intent: `rag`, `web_search`, or `direct_llm`.
2. **RAG Flow**: Query is embedded. Semantic vector search (via `pgvector`) combined with BM25 keyword search extracts candidate passages. Results are reranked using Cohere's Reranker.
3. **Web Search Flow**: Queries are sent to Tavily Search API for real-time web results.
4. **Direct LLM Flow**: Relies on general model knowledge.

### C. UI Rendering & Table Visualization
* The server responds with a structured JSON object containing the markdown answer text, key takeaways, and suggested followups.
* The frontend parser `parseMarkdown` in `ui/script.js`:
  * Detects multi-line code blocks and isolates them to maintain formatting.
  * Identifies tables (even loose tables without outer pipes) and renders them as styled HTML tables.

---

## 🚀 How to Start the Application

Ensure you have a running **PostgreSQL** instance (with the `vector` extension enabled) and a **Redis** server running.

### Option A: Local Run (Development)
1. Set up the local virtual environment and install packages:
   ```bash
   pip install -r requirements.txt
   ```
2. Run the application using the local batch script:
   * Double-click `start_server.bat` OR run:
     ```bash
     .venv\Scripts\uvicorn main:app --reload --port 1800
     ```
3. Open [http://localhost:1800/](http://localhost:1800/) in your browser.

### Option B: Docker Run (Containerized)
1. Build the Docker image:
   ```bash
   docker build -t hybridcache-rag-v2 .
   ```
2. Run the Docker container:
   * Override variables to connect to host databases:
     ```bash
     docker run -d \
       -p 1800:1800 \
       --env-file .env \
       -e DATABASE_URL=postgresql://username:password@host.docker.internal:5432/database_name \
       -e REDIS_HOST=host.docker.internal \
       --name hybridcache-app-v2 \
       hybridcache-rag-v2
     ```
3. Open [http://localhost:1800/](http://localhost:1800/) to access the application.
