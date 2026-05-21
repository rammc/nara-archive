// Downloads tab: poll /api/jobs every 2s when the tab is active and the
// browser tab is visible. Render compact job cards with progress, expand on
// click for details, and offer cancel / restart / remove.

(function () {
  const POLL_MS = 2000;
  const TAB_ID = "downloads";

  const $ = (sel) => document.querySelector(sel);
  const list = () => $("#jobs-list");
  const empty = () => $("#jobs-empty");

  const expanded = new Set();
  let timer = null;
  let lastSig = "";

  function activeTab() {
    return (location.hash || "").replace(/^#/, "").split("/")[0] || "discovery";
  }
  function shouldPoll() {
    return activeTab() === TAB_ID && document.visibilityState === "visible";
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function fmtBytes(n) {
    if (!n) return "0 B";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
    return `${n.toFixed(n >= 10 ? 0 : 1)} ${units[i]}`;
  }

  function fmtAgo(iso) {
    if (!iso) return "";
    const t = new Date(iso).getTime();
    const s = Math.round((Date.now() - t) / 1000);
    if (s < 60) return `${s}s ago`;
    if (s < 3600) return `${Math.round(s / 60)}m ago`;
    if (s < 86400) return `${Math.round(s / 3600)}h ago`;
    return new Date(iso).toLocaleString();
  }

  function statusClass(status) {
    if (status === "done") return "status-ok";
    if (status === "failed" || status === "interrupted") return "status-err";
    if (status === "cancelled") return "status-cancelled";
    if (status === "queued") return "status-queued";
    return "status-running";
  }

  function progressPct(job) {
    const t = job.progress?.total || 0;
    const c = job.progress?.current || 0;
    if (!t) return 0;
    return Math.min(100, Math.round((c / t) * 100));
  }

  const ACTIVE = new Set(["queued", "fetching_metadata", "downloading", "building_pdfs"]);
  const TERMINAL = new Set(["done", "failed", "cancelled", "interrupted"]);

  function manifestNameFromPath(p) {
    if (!p) return null;
    const base = p.split("/").pop() || "";
    const stem = base.replace(/\.json$/, "");
    if (stem === "manifest") return "default";
    const m = stem.match(/^manifest-(.+)$/);
    return m ? m[1] : null;
  }

  function jobActions(job) {
    const out = [];
    if (ACTIVE.has(job.status)) {
      out.push(`<button data-action="cancel" data-id="${escapeHtml(job.job_id)}">Cancel</button>`);
    }
    if (job.status === "done" && (job.result?.successful_pdfs ?? 0) > 0) {
      const name = manifestNameFromPath(job.result?.manifest_path);
      if (name) {
        out.push(
          `<button data-action="open-library" data-name="${escapeHtml(name)}">Open in Library</button>`,
        );
      }
      out.push(`<button data-action="reveal-output">Open output folder</button>`);
    }
    if (job.status === "failed" || job.status === "interrupted") {
      out.push(`<button data-action="restart" data-id="${escapeHtml(job.job_id)}">Restart</button>`);
    }
    if (TERMINAL.has(job.status)) {
      out.push(`<button data-action="remove" data-id="${escapeHtml(job.job_id)}">Remove from history</button>`);
    }
    return out.join("");
  }

  function renderJob(job) {
    const li = document.createElement("li");
    li.className = "job-card";
    li.dataset.id = job.job_id;
    if (expanded.has(job.job_id)) li.classList.add("expanded");

    const phaseLabel = job.progress?.phase || job.status;
    const cur = job.progress?.current || 0;
    const tot = job.progress?.total || 0;
    const bytes = job.progress?.bytes_downloaded || 0;
    const headline =
      job.name ||
      `Parent NAID ${job.parent_naid}`;

    const errorsBlock =
      job.result?.errors?.length
        ? `<div class="job-errors"><strong>Errors</strong><ul>${job.result.errors
            .slice(0, 5)
            .map((e) => `<li>${escapeHtml(e)}</li>`)
            .join("")}</ul></div>`
        : "";

    const manifestBlock = job.result?.manifest_path
      ? `<div class="muted">Manifest: <code>${escapeHtml(job.result.manifest_path)}</code></div>`
      : "";

    const manifestName = manifestNameFromPath(job.result?.manifest_path);
    const pdfListBlock =
      job.status === "done" && manifestName && (job.result?.successful_pdfs ?? 0) > 0
        ? `<div class="pdf-list" data-manifest="${escapeHtml(manifestName)}">
             <strong>Produced PDFs</strong>
             <ul class="pdf-list-items"><li class="muted">Loading…</li></ul>
           </div>`
        : "";

    li.innerHTML = `
      <div class="job-head" data-toggle>
        <div class="job-id-block">
          <span class="job-name">${escapeHtml(headline)}</span>
          <span class="job-sub muted">NAID ${escapeHtml(job.parent_naid)} · created ${escapeHtml(
            fmtAgo(job.created_at),
          )}</span>
        </div>
        <span class="status-badge ${statusClass(job.status)}">${escapeHtml(job.status)}</span>
      </div>
      <div class="job-progress">
        <div class="bar" style="--pct: ${progressPct(job)}%"><span></span></div>
        <div class="meta">
          <span>${escapeHtml(phaseLabel)}</span>
          <span>${cur.toLocaleString()} / ${tot.toLocaleString()}</span>
          ${bytes ? `<span>${fmtBytes(bytes)} downloaded</span>` : ""}
          ${job.progress?.current_naid ? `<span class="muted">NAID ${escapeHtml(job.progress.current_naid)}</span>` : ""}
        </div>
      </div>
      <div class="job-details" hidden>
        <dl class="kv">
          <dt>Job ID</dt><dd><code>${escapeHtml(job.job_id)}</code></dd>
          <dt>Rate</dt><dd>${job.rate} s / request</dd>
          ${job.filter_query ? `<dt>Filter</dt><dd><code>${escapeHtml(job.filter_query)}</code></dd>` : ""}
          ${job.started_at ? `<dt>Started</dt><dd>${escapeHtml(fmtAgo(job.started_at))}</dd>` : ""}
          ${job.completed_at ? `<dt>Completed</dt><dd>${escapeHtml(fmtAgo(job.completed_at))}</dd>` : ""}
          ${job.result?.successful_pdfs != null ? `<dt>Successful PDFs</dt><dd>${job.result.successful_pdfs}</dd>` : ""}
          ${job.result?.failed_pdfs != null ? `<dt>Failed PDFs</dt><dd>${job.result.failed_pdfs}</dd>` : ""}
        </dl>
        ${manifestBlock}
        ${pdfListBlock}
        ${errorsBlock}
      </div>
      <div class="job-actions">${jobActions(job)}</div>
    `;
    return li;
  }

  function renderAll(jobs) {
    // Cheap diff: skip re-render if nothing changed.
    const sig = JSON.stringify(jobs.map((j) => [j.job_id, j.status, j.progress?.current, j.progress?.total, j.progress?.bytes_downloaded]));
    if (sig === lastSig) return;
    lastSig = sig;

    const container = list();
    container.innerHTML = "";
    empty().hidden = jobs.length > 0;
    for (const j of jobs) container.appendChild(renderJob(j));

    // Re-apply expanded state.
    for (const id of expanded) {
      const li = container.querySelector(`.job-card[data-id="${CSS.escape(id)}"]`);
      if (li) {
        li.classList.add("expanded");
        li.querySelector(".job-details").hidden = false;
        loadPdfList(li);
      }
    }
  }

  async function fetchAndRender() {
    try {
      const resp = await fetch("/api/jobs");
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const body = await resp.json();
      renderAll(body.jobs || []);
    } catch (e) {
      // Silent fail — show last-known state. A noisy error here would
      // hammer the user every 2s.
      console.warn("jobs poll failed:", e);
    }
  }

  function start() {
    if (timer !== null) return;
    fetchAndRender();
    timer = setInterval(() => {
      if (shouldPoll()) fetchAndRender();
    }, POLL_MS);
  }
  function stop() {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  }

  function syncToTab() {
    if (shouldPoll()) start();
    else if (activeTab() !== TAB_ID) stop();
  }

  document.addEventListener("DOMContentLoaded", () => {
    syncToTab();
    window.addEventListener("hashchange", syncToTab);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible" && activeTab() === TAB_ID) {
        fetchAndRender();
      }
    });

    // Toggle expand / action buttons via delegated listener.
    list().addEventListener("click", async (e) => {
      const t = e.target;
      if (!(t instanceof HTMLElement)) return;
      if (t.closest("[data-toggle]")) {
        const card = t.closest(".job-card");
        if (!card) return;
        const id = card.dataset.id;
        const details = card.querySelector(".job-details");
        const isExpanded = card.classList.toggle("expanded");
        details.hidden = !isExpanded;
        if (isExpanded) {
          expanded.add(id);
          loadPdfList(card);
        } else {
          expanded.delete(id);
        }
        return;
      }
      const action = t.dataset.action;
      if (!action) return;
      e.stopPropagation();
      const id = t.dataset.id;
      try {
        if (action === "cancel" || action === "remove") {
          const r = await fetch(`/api/jobs/${encodeURIComponent(id)}`, { method: "DELETE" });
          if (!r.ok && r.status !== 204) throw new Error(`HTTP ${r.status}`);
          await fetchAndRender();
        } else if (action === "restart") {
          const r = await fetch(`/api/jobs/${encodeURIComponent(id)}/restart`, { method: "POST" });
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
          await fetchAndRender();
        } else if (action === "open-library") {
          const name = t.dataset.name;
          if (name) location.hash = `#library/${name}`;
        } else if (action === "reveal-output") {
          const r = await fetch("/api/config/reveal-output", { method: "POST" });
          if (!r.ok) throw new Error(`HTTP ${r.status}`);
        }
      } catch (err) {
        alert(`Action "${action}" failed: ${err.message}`);
      }
    });
  });

  // Cache so re-expanding a card doesn't re-hit the API.
  const pdfListCache = new Map();

  async function loadPdfList(card) {
    const holder = card.querySelector(".pdf-list");
    if (!holder) return;
    const name = holder.dataset.manifest;
    if (!name || holder.dataset.loaded === "1") return;
    let units = pdfListCache.get(name);
    try {
      if (!units) {
        const r = await fetch(`/api/library/${encodeURIComponent(name)}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const body = await r.json();
        units = body.file_units || [];
        pdfListCache.set(name, units);
      }
      const ul = holder.querySelector(".pdf-list-items");
      if (!ul) return;
      if (units.length === 0) {
        ul.innerHTML = `<li class="muted">No PDFs in this manifest.</li>`;
      } else {
        ul.innerHTML = units
          .filter((u) => u.pdf_path && u.status === "ok")
          .map((u) => {
            const href = `/pdfs/${encodeURI(u.pdf_path.replace(/^pdfs\//, ""))}`;
            const title = u.title || u.naid || "(untitled)";
            return `<li>
              <a href="${escapeHtml(href)}" target="_blank" rel="noopener">${escapeHtml(title)}</a>
              <span class="muted">${u.page_count || 0}p · ${fmtBytes(u.pdf_size_bytes || 0)}</span>
            </li>`;
          })
          .join("");
      }
      holder.dataset.loaded = "1";
    } catch (err) {
      const ul = holder.querySelector(".pdf-list-items");
      if (ul) ul.innerHTML = `<li class="error">Could not load PDF list: ${escapeHtml(err.message)}</li>`;
    }
  }

  // Expose so discovery.js can force a refresh after creating a job.
  window.__naraDownloads = {
    refresh: fetchAndRender,
  };
})();
