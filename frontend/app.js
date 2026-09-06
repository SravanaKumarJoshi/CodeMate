/**
 * CodeMate — Large Repository AI Assistant Frontend
 * Handles real-time chat, streaming indexing progress, file tree exploration,
 * clickable source inspection, interactive workflow architecture, and live request tracing.
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elements - Navigation & Status
  const tabChat = document.getElementById("tabChat");
  const tabWorkflow = document.getElementById("tabWorkflow");
  const chatView = document.getElementById("chatView");
  const workflowView = document.getElementById("workflowView");
  const repoSelect = document.getElementById("repoSelect");
  const healthPill = document.getElementById("healthPill");
  const healthText = document.getElementById("healthText");
  const llmModeText = document.getElementById("llmModeText");
  const ragChunkCount = document.getElementById("ragChunkCount");

  // DOM Elements - Indexing Banner
  const indexingBanner = document.getElementById("indexingBanner");
  const indexingTitle = document.getElementById("indexingTitle");
  const indexingCount = document.getElementById("indexingCount");
  const indexingProgressBar = document.getElementById("indexingProgressBar");
  const indexingStatusDetail = document.getElementById("indexingStatusDetail");
  const indexingPercent = document.getElementById("indexingPercent");
  const zipFileInput = document.getElementById("zipFileInput");

  // DOM Elements - Project Explorer
  const fileSearchInput = document.getElementById("fileSearchInput");
  const fileTreeContainer = document.getElementById("fileTreeContainer");
  const fileCountBadge = document.getElementById("fileCountBadge");

  // DOM Elements - Chat Area
  const chatForm = document.getElementById("chatForm");
  const messageInput = document.getElementById("messageInput");
  const messagesContainer = document.getElementById("messagesContainer");
  const welcomeCard = document.getElementById("welcomeCard");

  // DOM Elements - Workflow View
  const nodeInspectorCard = document.getElementById("nodeInspectorCard");
  const inspectorNodeTitle = document.getElementById("inspectorNodeTitle");
  const inspectorNodeContent = document.getElementById("inspectorNodeContent");
  const tracerRequestId = document.getElementById("tracerRequestId");
  const tracerDuration = document.getElementById("tracerDuration");
  const tracerQueryPreview = document.getElementById("tracerQueryPreview");
  const timelineContainer = document.getElementById("timelineContainer");

  // DOM Elements - Code Viewer Modal
  const fileModalBackdrop = document.getElementById("fileModalBackdrop");
  const modalFileName = document.getElementById("modalFileName");
  const modalLineRangeBadge = document.getElementById("modalLineRangeBadge");
  const modalLineNumbers = document.getElementById("modalLineNumbers");
  const modalFileContent = document.getElementById("modalFileContent");
  const modalCloseBtn = document.getElementById("modalCloseBtn");

  // Application State
  let activeRepoId = "repo_sample_project";
  let cachedFiles = [];
  let architectureData = {};
  let lastRequestId = null;
  let indexingPollTimer = null;

  // =========================================================================
  // 1. Navigation Tabs
  // =========================================================================
  tabChat.addEventListener("click", () => {
    tabChat.classList.add("active");
    tabWorkflow.classList.remove("active");
    chatView.classList.remove("hidden");
    workflowView.classList.add("hidden");
  });

  tabWorkflow.addEventListener("click", () => {
    tabWorkflow.classList.add("active");
    tabChat.classList.remove("active");
    workflowView.classList.remove("hidden");
    chatView.classList.add("hidden");

    if (lastRequestId) {
      loadWorkflowTrace(lastRequestId);
    }
  });

  // =========================================================================
  // 2. Health & Diagnostic Status
  // =========================================================================
  async function checkHealth() {
    try {
      const res = await fetch("/api/health");
      if (!res.ok) throw new Error("Health check failed");
      const data = await res.json();

      healthText.textContent = "Ready";
      healthPill.style.borderColor = "var(--accent-green)";

      if (data.llm_mode === "online") {
        llmModeText.textContent = "LLM: OpenAI Online";
        llmModeText.parentElement.style.borderColor = "var(--accent-green)";
      } else {
        llmModeText.textContent = "LLM: Offline Engine";
      }

      if (data.vector_db && typeof data.vector_db.indexed_chunks === "number") {
        ragChunkCount.textContent = `${data.vector_db.indexed_chunks} Chunks`;
      }
    } catch (err) {
      healthText.textContent = "Offline";
      healthPill.style.borderColor = "var(--accent-red)";
    }
  }

  // =========================================================================
  // 3. Repository Management & Indexing
  // =========================================================================
  async function loadRepositories() {
    try {
      const res = await fetch("/api/repositories");
      if (!res.ok) return;
      const data = await res.json();

      repoSelect.innerHTML = "";
      (data.repositories || []).forEach(r => {
        const opt = document.createElement("option");
        opt.value = r.id;
        opt.textContent = `${r.name} (${r.total_files || 0} files)`;
        if (r.is_active) {
          opt.selected = true;
          activeRepoId = r.id;
        }
        repoSelect.appendChild(opt);
      });

      loadProjectFiles();
    } catch (err) {
      console.warn("Failed to load repositories:", err);
    }
  }

  repoSelect.addEventListener("change", async (e) => {
    const selectedId = e.target.value;
    try {
      await fetch(`/api/repositories/${selectedId}/activate`, { method: "POST" });
      activeRepoId = selectedId;
      loadProjectFiles();
      checkHealth();
    } catch (err) {
      console.error("Failed to activate repository:", err);
    }
  });

  // Format byte counts into human-readable B, KB, MB, GB
  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return (bytes / Math.pow(k, i)).toFixed(i >= 2 ? 1 : 0) + " " + sizes[i];
  }

  // Streaming Large Upload Handling with XMLHttpRequest Progress
  zipFileInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);
    formData.append("repository_name", file.name.replace(/\.zip$/i, ""));

    const totalFormatted = formatBytes(file.size);
    showIndexingBanner("Repository Upload", 0, `0 B / ${totalFormatted}`, "Streaming directly to disk in 64 KB chunks...");

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/repositories/upload", true);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        const percent = Math.round((event.loaded / event.total) * 100);
        const loadedStr = formatBytes(event.loaded);
        const totalStr = formatBytes(event.total);
        showIndexingBanner(
          "Repository Upload",
          percent,
          `${loadedStr} / ${totalStr}`,
          `Streaming directly to disk (${percent}%)`
        );
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const uploadData = JSON.parse(xhr.responseText);
          const repoId = uploadData.repository_id;
          showIndexingBanner(
            "Extracting Repository",
            10,
            "Validating archive & filtering excluded folders...",
            "Checking Zip Slip, ignoring .git & dependency directories..."
          );
          pollIndexingProgress(repoId, file.name);
        } catch (err) {
          alert(`Invalid server response: ${err.message}`);
          hideIndexingBanner();
        }
      } else {
        let errDetail = "Upload failed";
        try {
          const errData = JSON.parse(xhr.responseText);
          errDetail = errData.detail || errDetail;
        } catch (e) {}
        alert(`Upload Error: ${errDetail}`);
        hideIndexingBanner();
      }
      zipFileInput.value = "";
    };

    xhr.onerror = () => {
      alert("Network error occurred during repository upload.");
      hideIndexingBanner();
      zipFileInput.value = "";
    };

    xhr.send(formData);
  });

  function showIndexingBanner(title, pct, countText, detailText) {
    indexingBanner.classList.remove("hidden");
    indexingTitle.textContent = title;
    indexingProgressBar.style.width = `${pct}%`;
    indexingPercent.textContent = `${pct}%`;
    if (countText !== undefined) indexingCount.textContent = countText;
    if (detailText !== undefined) indexingStatusDetail.textContent = detailText;
  }

  function hideIndexingBanner() {
    indexingBanner.classList.add("hidden");
    if (indexingPollTimer) clearInterval(indexingPollTimer);
  }

  function pollIndexingProgress(repoId, filename) {
    if (indexingPollTimer) clearInterval(indexingPollTimer);

    indexingPollTimer = setInterval(async () => {
      try {
        const res = await fetch(`/api/repositories/${repoId}/status`);
        if (!res.ok) return;
        const data = await res.json();

        const pct = Math.max(5, data.progress || 0);

        if (data.status === "indexing") {
          if (pct < 15) {
            indexingTitle.textContent = "Extracting Repository";
            indexingCount.textContent = "Safe extraction";
            indexingStatusDetail.textContent = "Filtering .git and dependency folders before extraction...";
          } else if (pct >= 15 && pct < 85) {
            indexingTitle.textContent = "Indexing Repository";
            const discovered = data.files_discovered || data.total_files || 0;
            const indexed = data.files_indexed || data.files_processed || 0;
            const skipped = data.files_skipped || 0;
            indexingCount.textContent = `Discovered: ${discovered.toLocaleString()} | Indexed: ${indexed.toLocaleString()} | Skipped: ${skipped.toLocaleString()}`;

            let skipDetail = "";
            if (data.skip_reasons && Object.keys(data.skip_reasons).length > 0) {
              const parts = [];
              for (const [cat, count] of Object.entries(data.skip_reasons)) {
                parts.push(`${count.toLocaleString()} ${cat.toLowerCase()}`);
              }
              skipDetail = `Skipped: ${parts.join(", ")}`;
            } else {
              skipDetail = `Generated ${data.chunks_created || 0} AST code chunks`;
            }
            indexingStatusDetail.textContent = skipDetail;
          } else {
            indexingTitle.textContent = "Generating embeddings...";
            indexingCount.textContent = `${data.files_processed || 0} / ${data.total_files || 0} files`;
            indexingStatusDetail.textContent = `Flushing ${data.chunks_created || 0} vector embeddings to ChromaDB...`;
          }

          indexingProgressBar.style.width = `${pct}%`;
          indexingPercent.textContent = `${pct}%`;

        } else if (data.status === "ready" || pct >= 100) {
          clearInterval(indexingPollTimer);
          indexingProgressBar.style.width = "100%";
          indexingPercent.textContent = "100%";
          indexingTitle.textContent = "✓ Repository indexed successfully";
          const discovered = data.files_discovered || data.total_files || 0;
          const indexed = data.files_indexed || data.files_processed || 0;
          const skipped = data.files_skipped || 0;
          indexingCount.textContent = `Indexed: ${indexed.toLocaleString()} / Discovered: ${discovered.toLocaleString()} (${skipped.toLocaleString()} skipped)`;

          let finalDetail = `Generated ${data.chunks_created || 0} chunks.`;
          if (data.skip_reasons && Object.keys(data.skip_reasons).length > 0) {
            const parts = [];
            for (const [cat, count] of Object.entries(data.skip_reasons)) {
              parts.push(`${count.toLocaleString()} ${cat.toLowerCase()}`);
            }
            finalDetail += ` (Skipped: ${parts.join(", ")})`;
          }
          indexingStatusDetail.textContent = finalDetail;

          setTimeout(() => {
            hideIndexingBanner();
            loadRepositories();
            checkHealth();
          }, 3000);

        } else if (data.status === "failed") {
          clearInterval(indexingPollTimer);
          alert(`Indexing Failed: ${data.error_message || "Unknown error"}`);
          hideIndexingBanner();
        }
      } catch (err) {
        console.warn("Polling error:", err);
      }
    }, 800);
  }

  // =========================================================================
  // 4. Project Explorer & File Tree
  // =========================================================================
  async function loadProjectFiles() {
    try {
      const res = await fetch(`/api/files?repository_id=${activeRepoId}`);
      if (!res.ok) return;
      const data = await res.json();

      cachedFiles = data.files || [];
      fileCountBadge.textContent = `${cachedFiles.length} files`;
      renderFileTree(cachedFiles);
    } catch (err) {
      fileTreeContainer.innerHTML = `<div class="empty-tree">Failed to load files</div>`;
    }
  }

  function renderFileTree(files) {
    if (!files || files.length === 0) {
      fileTreeContainer.innerHTML = `<div class="empty-tree">No eligible source files found</div>`;
      return;
    }

    fileTreeContainer.innerHTML = "";
    files.forEach(f => {
      const item = document.createElement("div");
      item.className = "tree-item";
      item.title = `Click to view ${f.path}`;

      const icon = getFileIcon(f.extension);
      item.innerHTML = `
        <div class="tree-item-name">
          <span>${icon}</span>
          <span>${f.path}</span>
        </div>
        <span class="tree-item-lines">${f.lines || 0}L</span>
      `;

      item.addEventListener("click", () => {
        openCodeViewer(f.path, 1, Math.min(100, f.lines || 100));
      });

      fileTreeContainer.appendChild(item);
    });
  }

  function getFileIcon(ext) {
    if (ext === ".py") return "🐍";
    if (ext === ".js" || ext === ".ts" || ext === ".jsx" || ext === ".tsx") return "📜";
    if (ext === ".json" || ext === ".yaml" || ext === ".yml") return "⚙️";
    if (ext === ".md" || ext === ".txt") return "📝";
    if (ext === ".sql") return "🗄️";
    return "📄";
  }

  // Live file filter
  fileSearchInput.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase().trim();
    if (!q) {
      renderFileTree(cachedFiles);
      return;
    }
    const filtered = cachedFiles.filter(f => f.path.toLowerCase().includes(q));
    renderFileTree(filtered);
  });

  // =========================================================================
  // 5. Code Viewer Modal with Line Numbers & Highlights
  // =========================================================================
  async function openCodeViewer(filePath, startLine = 1, endLine = 100) {
    modalFileName.textContent = filePath;
    modalLineRangeBadge.textContent = `Lines ${startLine}-${endLine}`;
    modalLineNumbers.innerHTML = "Loading...";
    modalFileContent.textContent = "Fetching file contents...";
    fileModalBackdrop.classList.add("active");

    try {
      const res = await fetch(`/api/files/content?file_path=${encodeURIComponent(filePath)}&repository_id=${activeRepoId}`);
      if (!res.ok) throw new Error("Could not read file");
      const data = await res.json();

      const lines = (data.content || "").split("\n");
      modalFileContent.textContent = data.content;

      // Render line numbers
      let lineNumsHtml = "";
      for (let i = 1; i <= lines.length; i++) {
        const isHighlighted = (i >= startLine && i <= endLine);
        lineNumsHtml += `<div style="${isHighlighted ? 'color: var(--accent-cyan); font-weight: bold;' : ''}">${i}</div>`;
      }
      modalLineNumbers.innerHTML = lineNumsHtml;

    } catch (err) {
      modalFileContent.textContent = `Error loading file: ${err.message}`;
    }
  }

  modalCloseBtn.addEventListener("click", () => {
    fileModalBackdrop.classList.remove("active");
  });

  fileModalBackdrop.addEventListener("click", (e) => {
    if (e.target === fileModalBackdrop) {
      fileModalBackdrop.classList.remove("active");
    }
  });

  // =========================================================================
  // 6. Chat Interaction
  // =========================================================================
  chatForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const query = messageInput.value.trim();
    if (!query) return;

    submitUserQuery(query);
  });

  // Quick Demo Buttons
  document.querySelectorAll(".demo-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const q = btn.getAttribute("data-query");
      if (q) {
        if (chatView.classList.contains("hidden")) {
          tabChat.click();
        }
        submitUserQuery(q);
      }
    });
  });

  async function submitUserQuery(query) {
    if (welcomeCard) welcomeCard.style.display = "none";

    appendUserMessage(query);
    messageInput.value = "";

    const loadingId = appendLoadingMessage();

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: query,
          repository_id: activeRepoId
        })
      });

      removeLoadingMessage(loadingId);

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Server failed to process query");
      }

      const data = await res.json();
      lastRequestId = data.request_id;

      appendAssistantMessage(data);

      // Pre-fetch workflow trace for the workflow tab
      loadWorkflowTrace(data.request_id);

    } catch (err) {
      removeLoadingMessage(loadingId);
      appendErrorMessage(`Assistant Error: ${err.message}`);
    }
  }

  function appendUserMessage(text) {
    const msg = document.createElement("div");
    msg.className = "chat-message message-user";
    msg.innerHTML = `
      <div class="message-avatar">👤</div>
      <div class="message-body">
        <p>${escapeHtml(text)}</p>
      </div>
    `;
    messagesContainer.appendChild(msg);
    scrollToBottom();
  }

  function appendLoadingMessage() {
    const id = "loading_" + Date.now();
    const msg = document.createElement("div");
    msg.id = id;
    msg.className = "chat-message message-assistant";
    msg.innerHTML = `
      <div class="message-avatar">🤖</div>
      <div class="message-body">
        <div style="display: flex; align-items: center; gap: 8px; color: var(--text-muted);">
          <span class="indexing-spinner"></span>
          <span>Routing via ML classifier, executing agent tools & querying ChromaDB...</span>
        </div>
      </div>
    `;
    messagesContainer.appendChild(msg);
    scrollToBottom();
    return id;
  }

  function removeLoadingMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  function appendAssistantMessage(data) {
    const msg = document.createElement("div");
    msg.className = "chat-message message-assistant";

    // Format tools badge
    const toolsStr = (data.tools_used && data.tools_used.length) ? data.tools_used.join(", ") : "rag_retrieval";

    // Render markdown answer
    const formattedAnswer = renderMarkdown(data.answer || "No response generated.");

    // Format citations chips
    let sourcesHtml = "";
    if (data.sources && data.sources.length) {
      sourcesHtml = `
        <div class="sources-container">
          <div class="sources-title">Verified Repository Sources:</div>
          <div class="source-chips">
      `;
      data.sources.forEach(s => {
        let f = s.file || (typeof s === "string" ? s : "file");
        let sLine = s.start_line || 1;
        let eLine = s.end_line || 60;
        sourcesHtml += `
          <button class="source-chip" data-file="${f}" data-start="${sLine}" data-end="${eLine}" title="Click to view ${f}:${sLine}-${eLine}">
            📄 ${f}:${sLine}-${eLine}
          </button>
        `;
      });
      sourcesHtml += `</div></div>`;
    }

    msg.innerHTML = `
      <div class="message-avatar">🤖</div>
      <div class="message-body">
        <div class="message-meta">
          <span class="intent-badge">${data.intent || "GENERAL_QUERY"}</span>
          <span class="tools-badge">Tools: ${toolsStr}</span>
          <span>⏱️ ${data.duration_ms || 0}ms</span>
        </div>
        <div class="message-text">${formattedAnswer}</div>
        ${sourcesHtml}
      </div>
    `;

    // Attach click handlers to source chips
    msg.querySelectorAll(".source-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        const file = chip.getAttribute("data-file");
        const s = parseInt(chip.getAttribute("data-start") || "1", 10);
        const e = parseInt(chip.getAttribute("data-end") || "80", 10);
        openCodeViewer(file, s, e);
      });
    });

    messagesContainer.appendChild(msg);
    scrollToBottom();
  }

  function appendErrorMessage(text) {
    const msg = document.createElement("div");
    msg.className = "chat-message message-assistant";
    msg.innerHTML = `
      <div class="message-avatar" style="background-color: var(--accent-red)">⚠️</div>
      <div class="message-body" style="border-color: var(--accent-red)">
        <p style="color: var(--accent-red)">${escapeHtml(text)}</p>
      </div>
    `;
    messagesContainer.appendChild(msg);
    scrollToBottom();
  }

  function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // =========================================================================
  // 7. Dedicated Interactive Workflow View
  // =========================================================================
  async function loadArchitectureSpecs() {
    try {
      const res = await fetch("/api/workflow/architecture");
      if (!res.ok) return;
      architectureData = await res.json();
    } catch (err) {
      console.warn("Could not load architecture metadata:", err);
    }
  }

  // Attach click listener to each architecture node
  document.querySelectorAll(".arch-node").forEach(node => {
    node.addEventListener("click", () => {
      document.querySelectorAll(".arch-node").forEach(n => n.classList.remove("active-inspector"));
      node.classList.add("active-inspector");

      const nodeKey = node.getAttribute("data-node");
      displayNodeInspection(nodeKey);
    });
  });

  function displayNodeInspection(nodeKey) {
    const spec = architectureData[nodeKey];
    if (!spec) {
      inspectorNodeTitle.textContent = "Component Details";
      inspectorNodeContent.innerHTML = "<p>Technical details not available for this node.</p>";
      return;
    }

    inspectorNodeTitle.textContent = spec.title || "Component Specification";

    let html = `<p><strong>Description:</strong> ${spec.description || ""}</p>`;
    if (spec.tech) html += `<p><strong>Technology:</strong> <code>${spec.tech}</code></p>`;
    if (spec.engine) html += `<p><strong>Engine:</strong> <code>${spec.engine}</code></p>`;
    if (spec.security) html += `<p><strong>Security Controls:</strong> ${spec.security}</p>`;
    if (spec.classes) html += `<p><strong>Supported Intents:</strong> ${spec.classes.map(c => `<code>${c}</code>`).join(", ")}</p>`;
    if (spec.guardrails) html += `<p><strong>Guardrails:</strong> ${spec.guardrails.map(g => `<code>${g}</code>`).join(", ")}</p>`;
    if (spec.available_tools) {
      html += `<p><strong>Registered Tools:</strong></p><ul>`;
      spec.available_tools.forEach(t => {
        html += `<li><code>${t.name}</code> — ${t.role}</li>`;
      });
      html += `</ul>`;
    }

    inspectorNodeContent.innerHTML = html;
  }

  // Live Request Lifecycle Trace
  async function loadWorkflowTrace(requestId) {
    if (!requestId) return;

    tracerRequestId.textContent = requestId;
    tracerDuration.textContent = "Polling trace...";

    try {
      const res = await fetch(`/api/workflow/${requestId}`);
      if (!res.ok) return;
      const data = await res.json();

      tracerRequestId.textContent = data.request_id;
      tracerDuration.textContent = `${data.duration_ms || 0}ms`;
      tracerQueryPreview.innerHTML = `<strong>Query:</strong> "${escapeHtml(data.query || "")}" &bull; Intent: <code>${data.intent}</code>`;

      renderTimeline(data.steps || []);
    } catch (err) {
      console.warn("Error fetching trace:", err);
    }
  }

  function renderTimeline(steps) {
    if (!steps || steps.length === 0) {
      timelineContainer.innerHTML = `<div class="timeline-empty">No execution steps logged for this request.</div>`;
      return;
    }

    timelineContainer.innerHTML = "";
    steps.forEach(step => {
      const row = document.createElement("div");
      row.className = "timeline-step";

      const isCompleted = step.status === "completed";
      const iconClass = isCompleted ? "status-completed" : "status-pending";
      const iconChar = isCompleted ? "✓" : "⏳";

      row.innerHTML = `
        <div class="step-status-icon ${iconClass}">${iconChar}</div>
        <div class="step-name-badge">${step.name}</div>
        <div class="step-detail">${escapeHtml(step.detail || "Executed")}</div>
        <div class="step-time">${step.timestamp ? step.timestamp.substring(11, 19) : ""}</div>
      `;

      timelineContainer.appendChild(row);
    });
  }

  // =========================================================================
  // 8. Markdown & Utility Helpers
  // =========================================================================
  function renderMarkdown(md) {
    if (!md) return "";
    let html = escapeHtml(md);

    // Code blocks with syntax formatting
    html = html.replace(/```([a-zA-Z0-9_]*)\n([\s\S]*?)```/g, (match, lang, code) => {
      return `<pre><code class="language-${lang}">${code.trim()}</code></pre>`;
    });

    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Bold
    html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

    // Headers
    html = html.replace(/^### (.*$)/gim, '<h4>$1</h4>');
    html = html.replace(/^## (.*$)/gim, '<h3>$1</h3>');

    // Bullet points
    html = html.replace(/^\- (.*$)/gim, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');

    // Line breaks
    html = html.replace(/\n\n/g, '<br><br>');

    return html;
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Initialization
  checkHealth();
  loadRepositories();
  loadArchitectureSpecs();
});
