// DOM Element References
const leftSidebar = document.getElementById("leftSidebar");
const toggleSidebarBtn = document.getElementById("toggleSidebarBtn");
const closeSidebarBtn = document.getElementById("closeSidebarBtn");
const detailsDrawer = document.getElementById("detailsDrawer");
const toggleDetailsBtn = document.getElementById("toggleDetailsBtn");
const closeDrawerBtn = document.getElementById("closeDrawerBtn");
const chatWindow = document.getElementById("chatWindow");
const chatEmptyState = document.getElementById("chatEmptyState");
const chatInput = document.getElementById("chatInput");
const sendBtn = document.getElementById("sendBtn");
const attachBtn = document.getElementById("attachBtn");
const settingsBtn = document.getElementById("settingsBtn");
const pdfFile = document.getElementById("pdfFile");
const attachmentBadge = document.getElementById("attachmentBadge");
const attachedFileName = document.getElementById("attachedFileName");
const clearAttachmentBtn = document.getElementById("clearAttachmentBtn");
const selectionSettingsPopover = document.getElementById("selectionSettingsPopover");
const pageOption = document.getElementById("pageOption");
const dynamicInputs = document.getElementById("dynamicInputs");
const indexedDocsList = document.getElementById("indexedDocsList");

// Inspector tab content elements
const result = document.getElementById("result");
const chunksList = document.getElementById("chunksList");
const jsonCode = document.getElementById("jsonCode");
const logsConsole = document.getElementById("logsConsole");
const progressList = document.getElementById("progressList");
const resultMetadata = document.getElementById("resultMetadata");

// Hidden search settings
const searchTopK = document.getElementById("searchTopK");
const searchDocFilter = document.getElementById("searchDocFilter");
const searchMinSim = document.getElementById("searchMinSim");
const searchRerank = document.getElementById("searchRerank");
const flushPreprocessedBtn = document.getElementById("flushPreprocessedBtn");

// Helper to generate a unique session ID
function generateUUID() {
    try {
        return crypto.randomUUID();
    } catch (e) {
        return 'session-' + Math.random().toString(36).substring(2, 15) + '-' + Math.random().toString(36).substring(2, 15);
    }
}

// Global states
const pageSessionId = generateUUID();
let selectedFile = null;
let uploadedPdfPath = "";
let pdfTotalPages = 0;
let docsLoaded = false;
let activeDocumentId = null;
let activeSessionId = pageSessionId;

// ================================================================
//  UI LAYOUT & TRANSITIONS
// ================================================================

// Toggle Left Sidebar (on Mobile)
if (toggleSidebarBtn) {
    toggleSidebarBtn.addEventListener("click", () => {
        leftSidebar.classList.add("sidebar-open");
    });
}
if (closeSidebarBtn) {
    closeSidebarBtn.addEventListener("click", () => {
        leftSidebar.classList.remove("sidebar-open");
    });
}

// Toggle Right Details Drawer
if (toggleDetailsBtn) {
    toggleDetailsBtn.addEventListener("click", () => {
        detailsDrawer.classList.toggle("hidden-drawer");
    });
}
if (closeDrawerBtn) {
    closeDrawerBtn.addEventListener("click", () => {
        detailsDrawer.classList.add("hidden-drawer");
    });
}

// Drawer Tabs Switching
document.querySelectorAll(".drawer-tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".drawer-tab-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        
        document.querySelectorAll(".drawer-tab-content").forEach(tc => tc.classList.add("hidden"));
        const tabContent = document.getElementById(`${btn.dataset.tab}Tab`);
        if (tabContent) {
            tabContent.classList.remove("hidden");
        }
    });
});

// Toggle Settings Popover
if (settingsBtn) {
    settingsBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        selectionSettingsPopover.classList.toggle("hidden");
    });
}

if (selectionSettingsPopover) {
    selectionSettingsPopover.addEventListener("click", (e) => {
        e.stopPropagation();
    });
}

document.addEventListener("click", () => {
    if (selectionSettingsPopover) {
        selectionSettingsPopover.classList.add("hidden");
    }
});

// ================================================================
//  PDF ATTACHMENT FLOW
// ================================================================

if (attachBtn) {
    attachBtn.addEventListener("click", () => {
        pdfFile.click();
    });
}

pdfFile.addEventListener("change", () => {
    const file = pdfFile.files[0];
    if (!file) return;

    selectedFile = file;
    attachedFileName.textContent = file.name;
    attachmentBadge.classList.remove("hidden");
    chatEmptyState.classList.add("hidden");
    chatInput.placeholder = "Add a query or press Send to index document...";
    chatInput.focus();
});

if (clearAttachmentBtn) {
    clearAttachmentBtn.addEventListener("click", () => {
        pdfFile.value = "";
        selectedFile = null;
        attachmentBadge.classList.add("hidden");
        chatInput.placeholder = "Ask anything about your documents...";
        
        const messages = chatWindow.querySelectorAll(".chat-msg");
        if (messages.length === 0) {
            chatEmptyState.classList.remove("hidden");
        }
    });
}

// Dynamic indexing input bounds (Single, Range, Custom)
pageOption.addEventListener("change", () => {
    const option = pageOption.value;
    dynamicInputs.innerHTML = "";

    if (option === "single") {
        dynamicInputs.innerHTML = `
            <div class="form-group slide-in">
                <label for="pageNumber">Page Number</label>
                <input type="number" id="pageNumber" min="1" placeholder="e.g. 1">
            </div>
        `;
    } else if (option === "range") {
        dynamicInputs.innerHTML = `
            <div class="form-row slide-in">
                <div class="form-group">
                    <label for="startPage">Start</label>
                    <input type="number" id="startPage" min="1" placeholder="e.g. 1">
                </div>
                <div class="form-group">
                    <label for="endPage">End</label>
                    <input type="number" id="endPage" min="1" placeholder="e.g. 5">
                </div>
            </div>
        `;
    } else if (option === "custom") {
        dynamicInputs.innerHTML = `
            <div class="form-group slide-in">
                <label for="pageList">Page List (comma-separated)</label>
                <input type="text" id="pageList" placeholder="e.g. 1, 3, 5">
            </div>
        `;
    }
});

// Trigger initial popover layout load
pageOption.dispatchEvent(new Event("change"));

// ================================================================
//  CHAT MESSAGE UTILITIES
// ================================================================

function appendChatMessage(sender, htmlContent, id = null) {
    // Hide empty state
    chatEmptyState.classList.add("hidden");

    const row = document.createElement("div");
    row.className = `chat-msg ${sender}`;
    if (id) row.id = id;

    if (sender === "assistant") {
        row.innerHTML = `
            <div class="chat-msg-avatar">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275z"></path>
                    <path d="m5 3 1 2.5L8.5 6 6 7 5 9.5 4 7 1.5 6 4 5.5z"></path>
                    <path d="m19 17 1 2.5 2.5.5-2.5 1-1 2.5-1-2.5-2.5-1 2.5-1z"></path>
                </svg>
            </div>
            <div class="chat-msg-bubble">${htmlContent}</div>
        `;
    } else {
        row.innerHTML = `
            <div class="chat-msg-bubble">${htmlContent}</div>
        `;
    }

    chatWindow.appendChild(row);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    return row;
}

function appendSystemMessage(text) {
    const row = document.createElement("div");
    row.className = "chat-msg system";
    row.innerHTML = `
        <div style="font-size: 11px; color: var(--text-secondary); background: rgba(15,23,42,0.6); padding: 4px 12px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.03);">
            ${text}
        </div>
    `;
    chatWindow.appendChild(row);
    chatWindow.scrollTop = chatWindow.scrollHeight;
}

function appendSystemProgressCard(filename, progressCardId) {
    // Hide empty state
    chatEmptyState.classList.add("hidden");

    const row = document.createElement("div");
    row.className = "chat-msg system";
    row.id = progressCardId;
    
    row.innerHTML = `
        <div class="system-progress-card">
            <div class="system-card-header">
                <svg class="spinner" viewBox="0 0 50 50"><circle class="path" cx="25" cy="25" r="20" fill="none" stroke-width="5"></circle></svg>
                <span class="card-status-title">Indexing: ${escapeHtml(filename)}</span>
            </div>
            <div class="progress-list">
                <!-- Progress steps filled here -->
            </div>
        </div>
    `;
    
    chatWindow.appendChild(row);
    chatWindow.scrollTop = chatWindow.scrollHeight;
    return row;
}

// ================================================================
//  INDEXED DOCUMENTS LIST & INSPECTOR
// ================================================================

async function loadIndexedDocuments() {
    try {
        const res = await fetch("/retriever/documents");
        const data = await res.json();
        if (data.success) {
            indexedDocsList.innerHTML = "";
            if (data.documents.length === 0) {
                indexedDocsList.innerHTML = '<div class="list-empty">No indexed documents. Attach a PDF below to start.</div>';
                return;
            }
            data.documents.forEach(doc => {
                const docItem = document.createElement("div");
                docItem.className = "doc-item";
                if (activeDocumentId === doc.document_id) {
                    docItem.classList.add("active");
                }
                
                docItem.innerHTML = `
                    <div class="doc-item-icon">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                    </div>
                    <div class="doc-item-info">
                        <span class="doc-item-title" title="${escapeHtml(doc.filename)}">${escapeHtml(doc.filename)}</span>
                        <span class="doc-item-meta">${doc.chunk_count} chunks · ID #${doc.document_id}</span>
                    </div>
                `;
                
                docItem.addEventListener("click", () => {
                    document.querySelectorAll(".doc-item").forEach(item => item.classList.remove("active"));
                    if (activeDocumentId === doc.document_id) {
                        activeDocumentId = null;
                        activeSessionId = pageSessionId;
                        if (searchDocFilter) searchDocFilter.value = "";
                        appendSystemMessage(`Cleared active document filter. Searching across all indexed files.`);
                    } else {
                        activeDocumentId = doc.document_id;
                        activeSessionId = doc.session_id || pageSessionId;
                        docItem.classList.add("active");
                        if (searchDocFilter) searchDocFilter.value = doc.document_id;
                        appendSystemMessage(`Filtering search queries to: <strong>${escapeHtml(doc.filename)}</strong>`);
                        inspectDocumentDetails(doc.document_id, doc.filename, doc.session_id);
                    }
                });
                
                indexedDocsList.appendChild(docItem);
            });
        }
    } catch (e) {
        console.warn("Could not load indexed documents:", e);
    }
}

async function inspectDocumentDetails(docId, filename, sessionId = null) {
    if (detailsDrawer.classList.contains("hidden-drawer")) {
        detailsDrawer.classList.remove("hidden-drawer");
    }
    
    // Set metadata headers
    resultMetadata.innerHTML = `
        <div class="meta-item">
            <span class="meta-label">Inspecting Document</span>
            <span class="meta-val">${escapeHtml(filename)}</span>
        </div>
        <div class="meta-item">
            <span class="meta-label">Document ID</span>
            <span class="meta-val">#${docId}</span>
        </div>
    `;

    // Retrieve doc chunks to display
    try {
        const res = await fetch("/retriever/retrieve", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                query: "*",
                top_k: 20,
                document_id: docId,
                min_similarity: 0,
                session_id: sessionId
            })
        });
        const data = await res.json();
        if (data.success && data.results) {
            // Render chunks
            chunksList.innerHTML = "";
            data.results.forEach((chunk, index) => {
                const card = document.createElement("div");
                card.className = "chunk-card";
                const headerText = chunk.header ? chunk.header : `Chunk ${index + 1}`;
                card.innerHTML = `
                    <div class="chunk-header">
                        <span class="chunk-title">${escapeHtml(headerText)}</span>
                        <span class="chunk-meta">Page ${chunk.page_no}</span>
                    </div>
                    <div class="chunk-body">${escapeHtml(chunk.chunk_text)}</div>
                `;
                chunksList.appendChild(card);
            });
            
            // Render JSON
            jsonCode.textContent = JSON.stringify(data.results, null, 2);
            
            // Clear pages grid since base64 files are only generated live during processing
            result.innerHTML = `<div class="drawer-empty-state">Visual page frames are available immediately during PDF upload. Chunks are loaded above.</div>`;
        }
    } catch (e) {
        console.error("Error loading document inspection chunks:", e);
    }
}

// ================================================================
//  PDF INDEXING PIPELINE
// ================================================================

async function startIndexingPipeline() {
    const file = selectedFile;
    if (!file) return;

    // Reset inputs
    pdfFile.value = "";
    selectedFile = null;
    attachmentBadge.classList.add("hidden");
    chatInput.placeholder = "Ask anything about your documents...";

    const progressCardId = `progress-${Date.now()}`;
    appendChatMessage("user", `Upload and index document: <strong>${escapeHtml(file.name)}</strong>`);
    appendSystemProgressCard(file.name, progressCardId);

    // Open right drawer to Logs tab automatically
    detailsDrawer.classList.remove("hidden-drawer");
    document.querySelectorAll(".drawer-tab-btn").forEach(b => b.classList.remove("active"));
    const logsTabBtn = document.querySelector('.drawer-tab-btn[data-tab="logs"]');
    if (logsTabBtn) logsTabBtn.classList.add("active");
    document.querySelectorAll(".drawer-tab-content").forEach(tc => tc.classList.add("hidden"));
    const logsTab = document.getElementById("logsTab");
    if (logsTab) logsTab.classList.remove("hidden");

    // Start logs polling
    let logInterval = setInterval(async () => {
        try {
            const res = await fetch("/stream-logs");
            if (res.ok) {
                const data = await res.json();
                if (data.logs && data.logs.length > 0) {
                    logsConsole.textContent = data.logs.join("\n");
                    logsConsole.scrollTop = logsConsole.scrollHeight;
                    updateCardProgressUI(progressCardId, data.logs);
                }
            }
        } catch (e) {
            console.error("Error polling logs", e);
        }
    }, 250);

    try {
        // Step 1: Upload
        const uploadFormData = new FormData();
        uploadFormData.append("file", file);

        const uploadResponse = await fetch("/upload-pdf", {
            method: "POST",
            body: uploadFormData
        });
        const uploadData = await uploadResponse.json();

        if (!uploadResponse.ok) {
            throw new Error(uploadData.detail || "Upload failed.");
        }

        uploadedPdfPath = uploadData.data.pdf_path;
        pdfTotalPages = uploadData.data.total_pages;
        activeSessionId = uploadData.data.session_id || pageSessionId;

        // Step 2: Index / Select Chunks
        const selectionMode = pageOption.value;
        let pageNumber = "";
        let startPage = "";
        let endPage = "";
        let pageList = "";

        if (selectionMode === "single") {
            const el = document.getElementById("pageNumber");
            if (el) pageNumber = el.value.trim();
        } else if (selectionMode === "range") {
            const startEl = document.getElementById("startPage");
            const endEl = document.getElementById("endPage");
            if (startEl) startPage = startEl.value.trim();
            if (endEl) endPage = endEl.value.trim();
        } else if (selectionMode === "custom") {
            const listEl = document.getElementById("pageList");
            if (listEl) pageList = listEl.value.trim();
        }

        const selectionFormData = new FormData();
        selectionFormData.append("pdf_path", uploadedPdfPath);
        selectionFormData.append("selection_mode", selectionMode);
        if (pageNumber) selectionFormData.append("page_number", pageNumber);
        if (startPage) selectionFormData.append("start_page", startPage);
        if (endPage) selectionFormData.append("end_page", endPage);
        if (pageList) selectionFormData.append("page_list", pageList);
        selectionFormData.append("enable_verbose", "true");
        if (activeSessionId) {
            selectionFormData.append("session_id", activeSessionId);
        }

        const selectionResponse = await fetch("/pdf-selection", {
            method: "POST",
            body: selectionFormData
        });

        const selectionData = await selectionResponse.json();

        if (!selectionResponse.ok) {
            throw new Error(selectionData.detail || "Indexing page rendering failed.");
        }

        // Successfully finished!
        clearInterval(logInterval);
        markCardProgressSuccess(progressCardId);
        
        // Show PDF rendered results in drawer
        displayDrawerResults(selectionData);

        appendChatMessage("assistant", `Indexing complete! I have successfully processed and stored **${escapeHtml(file.name)}** (${pdfTotalPages} page${pdfTotalPages > 1 ? 's' : ''}) in the pgvector database. You can now chat about it.`);
        
        // Reload docs list
        loadIndexedDocuments();

    } catch (err) {
        clearInterval(logInterval);
        markCardProgressFailed(progressCardId);
        appendChatMessage("assistant", `Indexing failed: **${err.message}**`);
    }
}

// System progress state configurations
const perplexitySteps = [
    {
        id: "render",
        title: "Rendering Visual Frames",
        desc: "Extracting high-resolution PNG pages...",
        triggers: {
            running: "Rendering page ",
            completed: "Rendering ready"
        }
    },
    {
        id: "docling",
        title: "Scanning Document Layout",
        desc: "Running AI document analysis layout parser...",
        triggers: {
            running: "Initializing Docling document converter...",
            completed: "Docling ready"
        }
    },
    {
        id: "extract",
        title: "Extracting Layout & Elements",
        desc: "Reading figures, layers, and tables...",
        triggers: {
            running: "Processing page ",
            completed: "Raw extraction complete"
        }
    },
    {
        id: "chunk",
        title: "Structuring Semantic Chunks",
        desc: "Generating contextual chunk boundaries...",
        triggers: {
            running: "Starting semantic chunking pipeline...",
            completed: "Pipeline completed successfully"
        }
    }
];

function updateCardProgressUI(cardId, logsArray) {
    const card = document.getElementById(cardId);
    if (!card) return;
    const progressList = card.querySelector(".progress-list");
    if (!progressList) return;

    let stepStates = {};
    perplexitySteps.forEach(step => {
        let isRunning = false;
        let isCompleted = false;
        let dynamicDesc = step.desc;

        for (let i = 0; i < logsArray.length; i++) {
            const logLine = logsArray[i];
            if (logLine.includes(step.triggers.completed)) {
                isCompleted = true;
            }
            if (logLine.includes(step.triggers.running)) {
                isRunning = true;
                if (step.id === "render" && logLine.includes("Rendering page")) {
                    dynamicDesc = logLine.replace("[INFO]", "").trim();
                }
                if (step.id === "extract" && logLine.includes("Processing page")) {
                    dynamicDesc = logLine.replace("[INFO]", "").trim();
                }
            }
        }

        let state = "pending";
        if (isCompleted) state = "completed";
        else if (isRunning) state = "running";

        stepStates[step.id] = { state, desc: dynamicDesc };
    });

    progressList.innerHTML = "";
    perplexitySteps.forEach(step => {
        const info = stepStates[step.id];
        const item = document.createElement("div");
        item.className = `progress-item ${info.state}`;

        let iconHTML = "";
        if (info.state === "pending") {
            iconHTML = `<div class="progress-status-icon"></div>`;
        } else if (info.state === "running") {
            iconHTML = `<div class="progress-status-icon"></div>`;
        } else if (info.state === "completed") {
            iconHTML = `
                <div class="progress-status-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                </div>
            `;
        }

        item.innerHTML = `
            ${iconHTML}
            <div class="progress-content">
                <span class="progress-title">${step.title}</span>
                <span class="progress-desc">${info.desc}</span>
            </div>
        `;
        progressList.appendChild(item);
    });
}

function markCardProgressSuccess(cardId) {
    const card = document.getElementById(cardId);
    if (!card) return;
    const header = card.querySelector(".system-card-header");
    if (header) {
        header.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--success)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
            <span style="color: var(--success);">Indexing Completed</span>
        `;
    }
}

function markCardProgressFailed(cardId) {
    const card = document.getElementById(cardId);
    if (!card) return;
    const header = card.querySelector(".system-card-header");
    if (header) {
        header.innerHTML = `
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--error)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            <span style="color: var(--error);">Indexing Failed</span>
        `;
    }
    const runningItem = card.querySelector(".progress-item.running");
    if (runningItem) {
        runningItem.className = "progress-item failed";
        const icon = runningItem.querySelector(".progress-status-icon");
        if (icon) {
            icon.innerHTML = `
                <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
            `;
        }
    }
}

function displayDrawerResults(selectionData) {
    // Set active document header metadata
    const fileName = uploadedPdfPath.split("/").pop().split("\\").pop();
    resultMetadata.innerHTML = `
        <div class="meta-item">
            <span class="meta-label">Inspecting Document</span>
            <span class="meta-val">${fileName}</span>
        </div>
        <div class="meta-item">
            <span class="meta-label">Total Pages</span>
            <span class="meta-val">${pdfTotalPages}</span>
        </div>
    `;

    // Render visual page card items
    result.innerHTML = "";
    if (selectionData.rendered_pages && selectionData.rendered_pages.length > 0) {
        selectionData.rendered_pages.forEach(page => {
            const pageCard = document.createElement("div");
            pageCard.className = "page-card";
            pageCard.innerHTML = `
                <div class="page-card-header">
                    <span>Page ${page.page_number}</span>
                    <span class="dimensions">${page.width}x${page.height} px</span>
                </div>
                <div class="page-card-body">
                    <img src="data:image/png;base64,${page.base64_image}" alt="Page ${page.page_number}" class="page-img">
                    <div class="img-overlay">
                        <button class="view-btn" onclick="viewFullScreen('data:image/png;base64,${page.base64_image}', ${page.page_number})">
                            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
                            View Fullscreen
                        </button>
                    </div>
                </div>
            `;
            result.appendChild(pageCard);
        });
    } else {
        result.innerHTML = `<div class="drawer-empty-state">No pages rendered. Check selection criteria.</div>`;
    }

    // Render semantic chunk items
    chunksList.innerHTML = "";
    if (selectionData.final_chunks && selectionData.final_chunks.length > 0) {
        selectionData.final_chunks.forEach((chunk, index) => {
            const card = document.createElement("div");
            card.className = "chunk-card";
            const headerText = chunk.content.header ? chunk.content.header : `Paragraph ${index + 1}`;
            card.innerHTML = `
                <div class="chunk-header">
                    <span class="chunk-title">${escapeHtml(headerText)}</span>
                    <span class="chunk-meta">Page ${chunk.page_number}</span>
                </div>
                <div class="chunk-body">${escapeHtml(chunk.content.content)}</div>
            `;
            chunksList.appendChild(card);
        });
    } else {
        chunksList.innerHTML = `<div class="drawer-empty-state">No semantic chunks extracted.</div>`;
    }

    // Render Raw JSON
    if (selectionData.final_chunks) {
        jsonCode.textContent = JSON.stringify(selectionData.final_chunks, null, 2);
    } else {
        jsonCode.textContent = "{}";
    }

    // Final Log flush
    if (selectionData.verbose_logs && selectionData.verbose_logs.length > 0) {
        logsConsole.textContent = selectionData.verbose_logs.join("\n");
    }
}

// Global fullscreen preview helper
window.viewFullScreen = function(base64Src, pageNum) {
    const viewer = document.createElement("div");
    viewer.className = "fullscreen-viewer";
    viewer.innerHTML = `
        <div class="viewer-content">
            <div class="viewer-header">
                <h3>Page ${pageNum} Frame</h3>
                <button class="close-viewer-btn" onclick="this.closest('.fullscreen-viewer').remove()">
                    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                </button>
            </div>
            <div class="viewer-body">
                <img src="${base64Src}" alt="Page ${pageNum} Frame">
            </div>
        </div>
    `;
    document.body.appendChild(viewer);
};

// ================================================================
//  CHAT QUESTION ANSWERING PIPELINE
// ================================================================

async function handleSendMessage() {
    // If a PDF is attached, we trigger indexing instead of normal chat query
    if (selectedFile) {
        startIndexingPipeline();
        return;
    }

    const query = chatInput.value.trim();
    if (!query) return;

    // Reset inputs
    chatInput.value = "";
    
    // Render user message bubble
    appendChatMessage("user", escapeHtml(query));

    // Render assistant loading bubble
    const assistantBubbleId = `assistant-bubble-${Date.now()}`;
    const assistantRow = appendChatMessage("assistant", `<div class="status-info" style="display:flex;align-items:center;gap:6px;"><svg class="spinner" style="width:14px;height:14px;" viewBox="0 0 50 50"><circle class="path" cx="25" cy="25" r="20" fill="none" stroke-width="5" stroke="var(--accent)"></circle></svg> <span>Generating response...</span></div>`, assistantBubbleId);
    const bubbleContent = assistantRow.querySelector(".chat-msg-bubble");

    // Build RAG parameters body
    const body = {
        query:          query,
        top_k:          parseInt(searchTopK.value)     || 5,
        min_similarity: parseFloat(searchMinSim.value) || 0,
        use_reranker:   searchRerank ? (searchRerank.value === "true") : true,
    };
    if (activeDocumentId) {
        body.document_id = activeDocumentId;
    }
    if (activeSessionId) {
        body.session_id = activeSessionId;
    }

    let hasResultReceived = false;
    try {
        const res = await fetch("/retriever/answer", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });

        if (!res.ok) {
            const data = await res.json();
            bubbleContent.innerHTML = `<span style="color: var(--error);">Error: ${escapeHtml(data.detail || "Request failed.")}</span>`;
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop(); // save incomplete line

            for (const line of lines) {
                const trimmed = line.trim();
                if (trimmed.startsWith("data: ")) {
                    const jsonStr = trimmed.slice(6);
                    try {
                        const data = JSON.parse(jsonStr);
                        if (data.type === "status") {
                            // Dynamically update the loader text next to the spinner
                            const statusTextEl = bubbleContent.querySelector("span");
                            if (statusTextEl) {
                                statusTextEl.innerHTML = escapeHtml(data.message);
                            }
                        } else if (data.type === "result") {
                            hasResultReceived = true;
                            const payload = data.payload;
                            // Render verbose logs in logs console drawer if present
                            if (payload.verbose_logs && payload.verbose_logs.length > 0) {
                                logsConsole.textContent = payload.verbose_logs.join("\n");
                                logsConsole.scrollTop = logsConsole.scrollHeight;
                            }
                            
                            // Render inspector details chunks
                            renderInspectorChunks(payload.results);

                            // Construct structured output HTML
                            let formattedHtml = parseMarkdown(payload.answer);

                            // Add key takeaways
                            if (payload.key_takeaways && payload.key_takeaways.length > 0) {
                                formattedHtml += `
                                    <div class="key-takeaways-box" style="margin-top: 14px; padding: 12px 14px; background: rgba(99, 102, 241, 0.04); border-left: 3px solid var(--accent); border-radius: 6px; font-size: 13px;">
                                        <div style="font-weight: 700; color: #a5b4fc; margin-bottom: 6px; text-transform: uppercase; font-size: 9px; letter-spacing: 0.5px;">Key Takeaways</div>
                                        <ul style="margin: 0 0 0 16px; padding: 0; list-style-type: disc;">
                                            ${payload.key_takeaways.map(t => `<li style="margin-bottom: 4px; color: var(--text-primary);">${escapeHtml(t)}</li>`).join("")}
                                        </ul>
                                    </div>
                                `;
                            }

                            // Add suggested follow-up questions
                            if (payload.suggested_followups && payload.suggested_followups.length > 0) {
                                formattedHtml += `
                                    <div class="followups-box" style="margin-top: 16px; display: flex; flex-direction: column; gap: 8px;">
                                        <div style="font-size: 9px; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px;">Suggested Follow-ups</div>
                                        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                                            ${payload.suggested_followups.map(f => `
                                                <button class="quick-start-chip" onclick="triggerQuickFollowup('${escapeHtml(f).replace(/'/g, "\\'")}')" style="text-align: left; border: 1px dashed rgba(99,102,241,0.25); background: rgba(99,102,241,0.03); color: #c7d2fe; padding: 6px 12px; font-size: 11px; border-radius: 20px; cursor: pointer; transition: all 0.2s ease;">
                                                    ${escapeHtml(f)}
                                                </button>
                                            `).join("")}
                                        </div>
                                    </div>
                                `;
                            }

                            bubbleContent.innerHTML = formattedHtml;
                            chatWindow.scrollTop = chatWindow.scrollHeight;
                        } else if (data.type === "error") {
                            bubbleContent.innerHTML = `<span style="color: var(--error);">Error: ${escapeHtml(data.detail)}</span>`;
                        }
                    } catch (e) {
                        console.error("Error parsing status stream token:", e);
                        bubbleContent.innerHTML = `<span style="color: var(--error);">Error rendering response: ${escapeHtml(e.message)}</span>`;
                    }
                }
            }
        }

        if (!hasResultReceived) {
            if (!bubbleContent.querySelector("span.error") && !bubbleContent.innerHTML.includes("Error:")) {
                bubbleContent.innerHTML = `<span style="color: var(--error);">Error: Stream ended abruptly without generating a response.</span>`;
            }
        }

    } catch (err) {
        console.error("Chat RAG answering connection error:", err);
        bubbleContent.innerHTML = `<span style="color: var(--error);">Could not connect to server. Is the backend running?</span>`;
    }
}


// Global window listener for quick follow-ups click handler
window.triggerQuickFollowup = function(query) {
    if (chatInput) {
        chatInput.value = query;
        handleSendMessage();
    }
};

function renderInspectorChunks(results) {
    if (!results || results.length === 0) {
        chunksList.innerHTML = `<div class="drawer-empty-state">No contexts retrieved for the last query.</div>`;
        jsonCode.textContent = "{}";
        return;
    }

    // Render retrieved contexts into Chunks Tab
    chunksList.innerHTML = "";
    results.forEach(r => {
        const card = document.createElement("div");
        card.className = "chunk-card";
        // Create an identifier we can anchor/scroll to
        card.id = `chunk-card-${r.rank}`;
        
        const overallAcc = r.overall_accuracy !== undefined ? r.overall_accuracy : Math.round(r.similarity * 100);
        const confidenceLabel = r.accuracy && r.accuracy.confidence_label ? r.accuracy.confidence_label : (overallAcc >= 85 ? "High" : (overallAcc >= 50 ? "Medium" : "Low"));
        const section = r.header ? r.header : "Untitled Section";
        const filename = r.document_title || r.filename || (r.source ? r.source.split("/").pop() : "AI Assistant");

        card.innerHTML = `
            <div class="chunk-header" style="flex-wrap: wrap; gap: 6px;">
                <div style="display:flex;align-items:center;gap:6px;">
                    <span class="result-rank">${r.rank}</span>
                    <span class="chunk-title">${escapeHtml(section)}</span>
                </div>
                <div style="font-size: 10px; font-weight: 700; color: #a5b4fc;">Accuracy: ${overallAcc}% (${confidenceLabel})</div>
            </div>
            <div class="chunk-meta" style="margin-top: -4px;">
                <span class="result-badge filename">${escapeHtml(filename)}</span>
                <span class="result-badge page">Page ${r.page_no}</span>
            </div>
            <div class="chunk-body" style="font-size: 12px; margin-top: 4px;">${escapeHtml(r.chunk_text)}</div>
        `;
        
        chunksList.appendChild(card);
    });

    // Render JSON tab
    jsonCode.textContent = JSON.stringify(results, null, 2);
}

// Helper: Escape HTML
function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

// ── Simple Markdown & Citation Parser Helper ──────────────────
function parseMarkdown(text) {
    if (!text) return "";
    
    // Escape HTML to prevent XSS
    let escaped = escapeHtml(text);
    
    // Extract multi-line triple backtick code blocks temporarily
    const codeBlocks = [];
    escaped = escaped.replace(/```(\w*)\r?\n?([\s\S]*?)\r?\n?```/g, (match, lang, code) => {
        const index = codeBlocks.length;
        codeBlocks.push({ lang: lang.trim(), code: code });
        return `\n__CODE_BLOCK_PLACEHOLDER_${index}__\n`;
    });

    // Bold: **text**
    escaped = escaped.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
    
    // Inline code: `code`
    escaped = escaped.replace(/`(.*?)`/g, "<code>$1</code>");
    
    // Highlight citations like [1], [2] as styled buttons that highlight inspector chunks
    escaped = escaped.replace(/\[(\d+)\]/g, (match, num) => {
        return `<button class="citation-badge" onclick="highlightInspectorChunk(${num})" style="cursor: pointer; border: 1px solid rgba(99, 102, 241, 0.4); hover: scale(1.05);">${match}</button>`;
    });
    
    // Parse lists, GFM tables, and paragraphs
    let lines = escaped.split("\n");

    // Pre-pass: convert TSV blocks (tab-separated tables) to GFM pipe-table format
    // Detect runs of 3+ consecutive lines each having 2+ tab characters
    let tsvConverted = [];
    let i2 = 0;
    while (i2 < lines.length) {
        const tabCount = (lines[i2].match(/\t/g) || []).length;
        if (tabCount >= 2) {
            // Collect all consecutive tab-rich lines as a TSV block
            let tsvBlock = [];
            while (i2 < lines.length && (lines[i2].match(/\t/g) || []).length >= 2) {
                tsvBlock.push(lines[i2]);
                i2++;
            }
            if (tsvBlock.length >= 2) {
                // Convert TSV block to GFM pipe table
                const pipeRows = tsvBlock.map(row => {
                    const cells = row.split("\t").map(c => c.trim());
                    return "| " + cells.join(" | ") + " |";
                });
                // Insert separator after first row
                const colCount = tsvBlock[0].split("\t").length;
                const separator = "| " + Array(colCount).fill("---").join(" | ") + " |";
                tsvConverted.push(pipeRows[0]);
                tsvConverted.push(separator);
                for (let j = 1; j < pipeRows.length; j++) tsvConverted.push(pipeRows[j]);
            } else {
                // Not enough rows for a table, keep as-is
                tsvBlock.forEach(l => tsvConverted.push(l));
            }
        } else {
            tsvConverted.push(lines[i2]);
            i2++;
        }
    }
    lines = tsvConverted;

    let inList = false;
    let inTable = false;
    let tableHeaderCells = null;
    let tableHasStartedBody = false;
    let formattedLines = [];
    
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i];
        let trimmed = line.trim();
        
        // Check if the line is a code block placeholder
        if (trimmed.startsWith("__CODE_BLOCK_PLACEHOLDER_")) {
            // Close open structures first
            if (inTable) {
                if (tableHeaderCells) {
                    formattedLines.push(`<p>${tableHeaderCells.join(" | ")}</p>`);
                    tableHeaderCells = null;
                }
                if (tableHasStartedBody) {
                    formattedLines.push(`</tbody></table></div>`);
                }
                inTable = false;
                tableHasStartedBody = false;
            }
            if (inList) {
                formattedLines.push("</ul>");
                inList = false;
            }
            
            // Extract index and restore code block
            const match = trimmed.match(/__CODE_BLOCK_PLACEHOLDER_(\d+)__/);
            if (match) {
                const idx = parseInt(match[1], 10);
                const block = codeBlocks[idx];
                const classAttr = block.lang ? ` class="language-${block.lang}"` : "";
                formattedLines.push(`<pre style="background: rgba(0, 0, 0, 0.3); border: 1px solid rgba(255, 255, 255, 0.08); padding: 12px; border-radius: 8px; overflow-x: auto; margin: 12px 0;"><code${classAttr} style="font-family: Consolas, Monaco, 'Andale Mono', monospace; font-size: 12px; color: #e2e8f0; white-space: pre;">${block.code}</code></pre>`);
            }
            continue;
        }

        // Check if line looks like a table row: has at least one pipe '|'
        let hasPipes = (trimmed.match(/\|/g) || []).length >= 1;
        let isTableRow = false;
        
        if (inTable) {
            isTableRow = hasPipes;
        } else {
            // Peek ahead to see if the next line is a separator row
            if (hasPipes && i + 1 < lines.length) {
                let nextTrimmed = lines[i + 1].trim();
                let nextHasPipes = (nextTrimmed.match(/\|/g) || []).length >= 1;
                let nextIsSeparator = nextHasPipes && /^[ \t|:-]+$/.test(nextTrimmed) && nextTrimmed.includes('-');
                if (nextIsSeparator) {
                    isTableRow = true;
                }
            }
        }
        
        if (isTableRow) {
            // Split and clean cells
            let cells = trimmed.split("|").map(c => c.trim());
            // If the row started and ended with pipes, the first and last elements of the split will be empty.
            if (cells[0] === "") cells.shift();
            if (cells[cells.length - 1] === "") cells.pop();
            
            // Check if it's a separator row (e.g. |---|---| or ---|---)
            let isSeparator = cells.length > 0 && cells.every(c => /^[ \t:-]+$/.test(c)) && trimmed.includes('-');
            
            if (!inTable) {
                // Potential header row
                inTable = true;
                tableHeaderCells = cells;
                tableHasStartedBody = false;
            } else {
                if (tableHeaderCells && isSeparator) {
                    // Valid separator row - emit table header
                    formattedLines.push(`<div class="table-wrapper"><table class="markdown-table"><thead><tr>`);
                    tableHeaderCells.forEach(cell => {
                        formattedLines.push(`<th>${cell}</th>`);
                    });
                    formattedLines.push(`</tr></thead><tbody>`);
                    tableHeaderCells = null; // cleared
                    tableHasStartedBody = true;
                } else if (tableHeaderCells) {
                    // Not a separator row, but we had a pending header.
                    // This means it's not a valid table format, treat both as normal lines
                    formattedLines.push(`<p>${tableHeaderCells.join(" | ")}</p>`);
                    tableHeaderCells = null;
                    inTable = false;
                    
                    // Process this row as normal text
                    formattedLines.push(`<p>${line}</p>`);
                } else if (tableHasStartedBody) {
                    // Regular data row
                    formattedLines.push(`<tr>`);
                    cells.forEach(cell => {
                        formattedLines.push(`<td>${cell}</td>`);
                    });
                    formattedLines.push(`</tr>`);
                }
            }
        } else {
            // Not a table row
            if (inTable) {
                if (tableHeaderCells) {
                    // Had a pending header that was never confirmed with a separator
                    formattedLines.push(`<p>${tableHeaderCells.join(" | ")}</p>`);
                    tableHeaderCells = null;
                }
                if (tableHasStartedBody) {
                    formattedLines.push(`</tbody></table></div>`);
                }
                inTable = false;
                tableHasStartedBody = false;
            }
            
            // Handle lists and paragraphs
            if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
                if (!inList) {
                    formattedLines.push("<ul>");
                    inList = true;
                }
                formattedLines.push(`<li>${trimmed.slice(2)}</li>`);
            } else {
                if (inList) {
                    formattedLines.push("</ul>");
                    inList = false;
                }
                if (trimmed) {
                    formattedLines.push(`<p>${line}</p>`);
                }
            }
        }
    }
    
    // Close any open lists or tables at end of text
    if (inList) {
        formattedLines.push("</ul>");
    }
    if (inTable) {
        if (tableHeaderCells) {
            formattedLines.push(`<p>${tableHeaderCells.join(" | ")}</p>`);
        }
        if (tableHasStartedBody) {
            formattedLines.push(`</tbody></table></div>`);
        }
    }
    
    return formattedLines.join("");
}

// Action: Highlights a chunk card inside the inspector details drawer
window.highlightInspectorChunk = function(rankNum) {
    // Open drawer
    if (detailsDrawer.classList.contains("hidden-drawer")) {
        detailsDrawer.classList.remove("hidden-drawer");
    }
    
    // Switch to Chunks tab
    document.querySelectorAll(".drawer-tab-btn").forEach(b => b.classList.remove("active"));
    const chunksTabBtn = document.querySelector('.drawer-tab-btn[data-tab="chunks"]');
    if (chunksTabBtn) chunksTabBtn.classList.add("active");
    document.querySelectorAll(".drawer-tab-content").forEach(tc => tc.classList.add("hidden"));
    const chunksTab = document.getElementById("chunksTab");
    if (chunksTab) chunksTab.classList.remove("hidden");

    // Scroll to the specific card
    setTimeout(() => {
        const card = document.getElementById(`chunk-card-${rankNum}`);
        if (card) {
            card.scrollIntoView({ behavior: "smooth", block: "center" });
            
            // Add a brief glow outline flash effect
            card.style.borderColor = "var(--accent)";
            card.style.boxShadow = "0 0 16px rgba(99, 102, 241, 0.4)";
            setTimeout(() => {
                card.style.borderColor = "";
                card.style.boxShadow = "";
            }, 1800);
        }
    }, 100);
};

async function handleFlushPreprocessed() {
    if (!confirm("Are you sure you want to delete all cached images, tables, and preprocessed document chunks? This will clear the visual page frames and cache but preserve indexed database metadata.")) {
        return;
    }
    
    const originalText = flushPreprocessedBtn.innerHTML;
    flushPreprocessedBtn.disabled = true;
    flushPreprocessedBtn.style.opacity = "0.6";
    flushPreprocessedBtn.innerHTML = `
        <svg class="spinner" style="animation: spin 1.5s linear infinite; display: inline-block; vertical-align: middle; margin-right: 4px;" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="2" x2="12" y2="6"></line><line x1="12" y1="18" x2="12" y2="22"></line><line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line><line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line><line x1="2" y1="12" x2="6" y2="12"></line><line x1="18" y1="12" x2="22" y2="12"></line><line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line><line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line></svg>
        <span>Clearing...</span>
    `;

    try {
        const response = await fetch("/preprocessed/clear-cache", {
            method: "POST"
        });
        const data = await response.json();
        
        if (response.ok) {
            alert(data.message || "Preprocessed cache cleared successfully.");
            loadIndexedDocuments();
            result.innerHTML = `<div class="drawer-empty-state">No rendered pages. Index a PDF to view visual frames.</div>`;
            chunksList.innerHTML = `<div class="drawer-empty-state">No semantic chunks extracted.</div>`;
            jsonCode.textContent = "{}";
            resultMetadata.innerHTML = `<div class="meta-item-empty">No active document inspection.</div>`;
        } else {
            alert("Error: " + (data.detail || "Failed to clear preprocessed cache."));
        }
    } catch (err) {
        console.error("Flush preprocessed cache error:", err);
        alert("Could not connect to the server to clear preprocessed cache.");
    } finally {
        flushPreprocessedBtn.disabled = false;
        flushPreprocessedBtn.style.opacity = "1";
        flushPreprocessedBtn.innerHTML = originalText;
    }
}

// Collapsible raw console logs event listener
document.addEventListener("click", (e) => {
    const toggleBtn = e.target.closest("#toggleConsoleBtn");
    if (toggleBtn) {
        const wrapper = document.getElementById("rawConsoleWrapper");
        if (wrapper) {
            wrapper.classList.toggle("hidden");
            toggleBtn.classList.toggle("open");
            if (wrapper.classList.contains("hidden")) {
                toggleBtn.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
                    Show Raw Developer Logs
                `;
            } else {
                toggleBtn.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg>
                    Hide Raw Developer Logs
                `;
            }
        }
    }
});

// ================================================================
//  EVENT LISTENERS & STARTUP
// ================================================================

// Send Button handlers
sendBtn.addEventListener("click", handleSendMessage);
chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") handleSendMessage();
});

// Quick start suggestion chips handlers
document.querySelectorAll(".quick-start-chip").forEach(chip => {
    chip.addEventListener("click", () => {
        chatInput.value = chip.dataset.query;
        handleSendMessage();
    });
});

// Clear Preprocessed Cache Button handler
if (flushPreprocessedBtn) {
    flushPreprocessedBtn.addEventListener("click", handleFlushPreprocessed);
}

// Load document list in sidebar on startup
document.addEventListener("DOMContentLoaded", () => {
    loadIndexedDocuments();
});