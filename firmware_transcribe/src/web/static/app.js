/* Dashboard Mesin Transcribe — client logic (SSE real-time) */
"use strict";

const $ = (id) => document.getElementById(id);

const dropzone = $("dropzone");
const fileInput = $("file-input");
const btnTranscribe = $("btn-transcribe");
const btnCancel = $("btn-cancel");
const btnAINotulen = $("btn-ai-notulen");
const btnDownloadDocx = $("btn-download-docx");
const progressBar = $("progress-bar");
const progressLabel = $("progress-label");
const statusText = $("status-text");
const logEl = $("log");
const previewEl = $("preview");
const historyEl = $("history");

let selectedFile = null;   // File object (client)
let uploadedPath = null;   // path di server setelah upload
let currentJobId = null;
let eventSource = null;
let running = false;
let aiRunning = false;     // job AI notulen sedang berjalan
let resultFiles = {};      // folder hasil → file list
let currentResultPath = null;   // path absolut folder hasil terpilih
let currentResultFiles = [];    // daftar file di folder hasil terpilih

// ── Environment check ────────────────────────────────────────────────
async function checkEnv() {
  try {
    const r = await fetch("/api/env");
    const env = await r.json();
    const ff = env.ffmpeg.ok
      ? `<span class="ok">✅ ffmpeg OK</span>`
      : `<span class="warn">⚠️ ${env.ffmpeg.error}</span>`;
    const model = env.model_cached
      ? `<span class="ok">model small tersedia</span>`
      : `<span class="warn">model small belum di cache</span>`;
    const ai = env.ai
      ? `<span class="ok">AI ${env.ai.model}</span>`
      : "";
    $("env-status").innerHTML = `${ff} · ${model} · ${ai}`;

    // Settings persistence: prefill dari config tersimpan
    if (env.settings) {
      if (env.settings.model && [...$("model").options].some(o => o.value === env.settings.model)) {
        $("model").value = env.settings.model;
      }
      if (env.settings.language && [...$("language").options].some(o => o.value === env.settings.language)) {
        $("language").value = env.settings.language;
      }
    }
  } catch (e) {
    $("env-status").innerHTML = `<span class="warn">⚠️ tidak bisa hubungi server</span>`;
  }
}

// ── Drop zone / file picker ──────────────────────────────────────────
dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("dragover");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("dragover");
  if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) setFile(fileInput.files[0]);
});

function setFile(file) {
  selectedFile = file;
  uploadedPath = null;
  $("file-name").textContent = file.name;
  $("file-meta").textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB · ${file.type || "audio"}`;
  $("file-info").classList.remove("hidden");
  btnTranscribe.disabled = false;
  log(`File dipilih: ${file.name}`);
}

// ── Upload + transcribe ──────────────────────────────────────────────
btnTranscribe.addEventListener("click", async () => {
  if (!selectedFile) return;
  btnTranscribe.disabled = true;
  running = true;
  btnCancel.disabled = false;
  resetResult();
  setProgress(0, "");
  statusText.textContent = "Mengunggah file...";
  log("Mengunggah file ke server...");

  try {
    // 1. Upload
    const fd = new FormData();
    fd.append("file", selectedFile);
    const upRes = await fetch("/api/upload", { method: "POST", body: fd });
    if (!upRes.ok) {
      const err = await upRes.json().catch(() => ({}));
      throw new Error(err.detail || "Upload gagal");
    }
    const up = await upRes.json();
    uploadedPath = up.path;
    log(`Upload selesai: ${up.filename} (${(up.size / 1024 / 1024).toFixed(2)} MB)`);

    // 2. Start transcribe job
    const body = {
      audio_path: uploadedPath,
      model: $("model").value,
      language: $("language").value,
    };
    const jRes = await fetch("/api/transcribe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!jRes.ok) {
      const err = await jRes.json().catch(() => ({}));
      throw new Error(err.detail || "Gagal memulai transkripsi");
    }
    const job = await jRes.json();
    currentJobId = job.id;
    log(`Job dimulai: ${job.id} (model=${body.model}, bahasa=${body.language})`);
    statusText.textContent = "Transkripsi berjalan...";
    connectSSE(job.id);
  } catch (e) {
    setError(e.message);
  }
});

// ── SSE stream ───────────────────────────────────────────────────────
function connectSSE(jobId) {
  if (eventSource) eventSource.close();
  eventSource = new EventSource(`/api/jobs/${jobId}/stream`);

  eventSource.addEventListener("log", (ev) => {
    log(JSON.parse(ev.data).message);
  });
  eventSource.addEventListener("progress", (ev) => {
    const d = JSON.parse(ev.data);
    setProgress(d.percent, d.message);
  });
  eventSource.addEventListener("segment", (ev) => {
    const d = JSON.parse(ev.data);
    logSegment(d.start, d.text);
  });
  eventSource.addEventListener("finished", (ev) => {
    const d = JSON.parse(ev.data);
    if (aiRunning) {
      // Job AI notulen selesai
      aiRunning = false;
      statusText.textContent = "✅ Notulen AI selesai.";
      if (d.metadata && d.metadata.docx_path) setDocxLink(d.metadata.docx_path);
      loadResult(d.output_dir, d.metadata);
      showTab("ai");
      return;
    }
    statusText.textContent = "✅ Selesai.";
    resultFiles = d.output_dir || "";
    loadResult(d.output_dir, d.metadata);
  });
  eventSource.addEventListener("error", (ev) => {
    setError(JSON.parse(ev.data).error);
  });
  eventSource.addEventListener("cancelled", () => {
    statusText.textContent = "⛔ Dibatalkan.";
    log("Transkripsi dibatalkan user.");
    setProgress(0, "dibatalkan");
    endJob();
  });
  eventSource.addEventListener("job_end", (ev) => {
    endJob();
  });
  eventSource.onerror = () => {
    // EventSource reconnect otomatis; tutup jika job sudah selesai
    if (!running) eventSource.close();
  };
}

function endJob() {
  if (eventSource) { eventSource.close(); eventSource = null; }
  running = false;
  btnCancel.disabled = true;
  btnAINotulen.disabled = false;
  refreshHistory();
}

// ── Cancel ───────────────────────────────────────────────────────────
btnCancel.addEventListener("click", async () => {
  if (!currentJobId) return;
  statusText.textContent = "Membatalkan...";
  btnCancel.disabled = true;
  try {
    await fetch(`/api/jobs/${currentJobId}/cancel`, { method: "POST" });
  } catch (e) { /* biarkan SSE menangani */ }
});

// ── Hasil (preview TXT/JSON/Notulen AI + folder) ────────────────────
function resetResult() {
  previewEl.textContent = "—";
  $("result-actions").hidden = true;
  btnDownloadDocx.classList.add("hidden");
  document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
  document.querySelector('.tab[data-tab="txt"]').classList.add("active");
}

function setDocxLink(docxPath) {
  const folderName = docxPath.split(/[\\/]/).pop() === docxPath
    ? currentResultPath.split(/[\\/]/).pop()
    : docxPath.split(/[\\/]/).slice(-2, -1)[0];
  const fileName = docxPath.split(/[\\/]/).pop();
  btnDownloadDocx.href =
    `/api/history/${encodeURIComponent(folderName)}/file/${encodeURIComponent(fileName)}?download=1`;
  btnDownloadDocx.classList.remove("hidden");
}

async function loadResult(outputDir, metadata) {
  const folderName = outputDir.split(/[\\/]/).pop();
  resultFiles = folderName;
  currentResultPath = outputDir;
  $("result-actions").hidden = false;
  $("result-path").textContent = outputDir;
  $("btn-open-folder").href = `file:///${outputDir.replace(/\\/g, "/")}`;
  log(`✅ Selesai. Output: ${outputDir}`);
  if (metadata) {
    log(`   Segmen: ${metadata.segment_count} · proses: ${metadata.duration_s}s · audio: ${metadata.audio_duration_s}s`);
  }
  showTab("txt");
  refreshHistory();
}

document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => showTab(tab.dataset.tab));
});

async function showTab(tab) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
  document.querySelector(`.tab[data-tab="${tab}"]`).classList.add("active");
  if (!resultFiles) return;

  if (tab === "ai") {
    previewEl.textContent = "Memuat...";
    try {
      const r = await fetch(`/api/history/${encodeURIComponent(resultFiles)}/file/notulen_ai.txt`);
      if (!r.ok) {
        previewEl.textContent =
          "Belum ada notulen AI untuk hasil ini. Klik tombol \"🤖 Buat Notulen AI\" untuk merangkum transkrip dengan AI (hasilnya file DOCX).";
        return;
      }
      const d = await r.json();
      previewEl.textContent = d.content.length > 200000
        ? d.content.slice(0, 200000) + "\n...(dipotong)"
        : d.content;
    } catch (e) {
      previewEl.textContent = `Gagal memuat: ${e.message}`;
    }
    return;
  }

  const fileName = tab === "txt" ? "transkrip.txt" : "transkrip.json";
  const path = `/api/history/${encodeURIComponent(resultFiles)}/file/${fileName}`;
  previewEl.textContent = "Memuat...";
  try {
    const r = await fetch(path);
    if (!r.ok) {
      previewEl.textContent = `(file ${fileName} tidak tersedia)`;
      return;
    }
    const d = await r.json();
    const content = d.content.length > 200000
      ? d.content.slice(0, 200000) + "\n...(dipotong)"
      : d.content;
    previewEl.textContent = content;
  } catch (e) {
    previewEl.textContent = `Gagal memuat: ${e.message}`;
  }
}

// ── Notulen AI (Phase 2) ─────────────────────────────────────────────
btnAINotulen.addEventListener("click", async () => {
  if (!currentResultPath || aiRunning) return;
  if (running) {
    statusText.textContent = "Tunggu transkripsi selesai dulu.";
    return;
  }
  aiRunning = true;
  btnAINotulen.disabled = true;
  statusText.textContent = "🤖 AI menyusun notulen...";
  log("Memanggil AI notulen (9router lokal)...");
  try {
    const r = await fetch("/api/notulen/ai", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ output_dir: currentResultPath }),
    });
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.detail || "Gagal memulai AI notulen");
    }
    const job = await r.json();
    currentJobId = job.id;
    log(`Job AI dimulai: ${job.id}`);
    connectSSE(job.id);
  } catch (e) {
    setError(e.message);
    aiRunning = false;
    btnAINotulen.disabled = false;
  }
});

// ── History ──────────────────────────────────────────────────────────
async function refreshHistory() {
  try {
    const r = await fetch("/api/history");
    const d = await r.json();
    historyEl.innerHTML = "";
    if (!d.items.length) {
      historyEl.innerHTML = '<li class="empty">Belum ada hasil.</li>';
      return;
    }
    d.items.forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item.name;
      li.title = item.path;
      li.addEventListener("click", () => {
        document.querySelectorAll(".history li").forEach((x) => x.classList.remove("active"));
        li.classList.add("active");
        resultFiles = item.name;
        currentResultPath = item.path;
        currentResultFiles = item.files || [];
        $("result-actions").hidden = false;
        $("result-path").textContent = item.path;
        $("btn-open-folder").href = `file:///${item.path.replace(/\\/g, "/")}`;
        // Tampilkan link download kalau NotulenAI_*.docx sudah ada
        const docx = currentResultFiles.find((f) => f.toLowerCase().endsWith(".docx"));
        if (docx) setDocxLink(`${item.path}/${docx}`);
        else btnDownloadDocx.classList.add("hidden");
        showTab("txt");
      });
      historyEl.appendChild(li);
    });
  } catch (e) { /* diam */ }
}

// ── Helpers ──────────────────────────────────────────────────────────
function setProgress(pct, msg) {
  progressBar.style.width = `${pct}%`;
  progressLabel.textContent = `${pct}%`;
  if (msg) statusText.textContent = msg;
}

function setError(msg) {
  statusText.textContent = "❌ Error.";
  log(`❌ ${msg}`, "err");
  setProgress(0, "error");
  endJob();
}

function log(msg, cls = "") {
  const line = document.createElement("div");
  const time = new Date().toLocaleTimeString("id-ID", { hour12: false });
  if (cls) line.className = cls;
  line.textContent = `[${time}] ${msg}`;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}

function logSegment(start, text) {
  const line = document.createElement("div");
  line.className = "seg";
  const preview = text.length > 150 ? text.slice(0, 147) + "..." : text;
  line.textContent = `[${Math.floor(start)}s] ${preview}`;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}

// ── Init ─────────────────────────────────────────────────────────────
checkEnv();
refreshHistory();
