// Library tab: list manifests, drill into one, search, preview a PDF in a
// side panel via the browser's built-in viewer (iframe → /pdfs/...).

(function () {
  const $ = (s) => document.querySelector(s);

  function escapeHtml(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function fmtBytes(n) {
    if (!n) return "0 B";
    const u = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return `${n.toFixed(n >= 10 ? 0 : 1)} ${u[i]}`;
  }

  function fmtDate(iso) {
    if (!iso) return "—";
    try { return new Date(iso).toLocaleString(); }
    catch { return iso; }
  }

  function parseHash() {
    const raw = (location.hash || "").replace(/^#/, "");
    const [tab, name] = raw.split("/");
    return { tab: tab || "discovery", name: name || null };
  }

  // ---- list view ----

  async function loadList() {
    try {
      const r = await fetch("/api/library");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      renderList((await r.json()).manifests || []);
    } catch (e) {
      $("#library-empty").textContent = `Couldn't load: ${e.message}`;
    }
  }

  function renderList(items) {
    const wrap = $("#library-cards");
    wrap.innerHTML = "";
    $("#library-empty").hidden = items.length > 0;
    for (const m of items) {
      const li = document.createElement("li");
      li.className = "card";
      li.innerHTML = `
        <div class="thumb thumb-empty" aria-hidden="true">📁</div>
        <div class="card-body">
          <h3>${escapeHtml(m.parent_title || m.name)}</h3>
          <div class="meta">
            <span class="badge">${escapeHtml(m.name)}</span>
            ${m.parent_naid ? `<span class="meta-naid">NAID ${escapeHtml(m.parent_naid)}</span>` : ""}
            <span>${m.file_unit_count} file units</span>
            <span>${m.pdf_count} PDFs</span>
            <span>${fmtBytes(m.total_size_bytes)}</span>
            <span class="muted">generated ${escapeHtml(fmtDate(m.generated_at))}</span>
          </div>
          <div class="card-actions">
            <a class="link-btn" href="#library/${encodeURIComponent(m.name)}">Open</a>
          </div>
        </div>
      `;
      wrap.appendChild(li);
    }
  }

  // ---- detail view ----

  let currentName = null;
  let currentUnits = [];
  let searchDebounce = null;

  async function loadDetail(name) {
    currentName = name;
    $("#library-title").textContent = "loading…";
    $("#library-sub").textContent = "";
    $("#library-units").innerHTML = "";
    $("#library-search").value = "";
    closePdf();

    try {
      const r = await fetch(`/api/library/${encodeURIComponent(name)}`);
      if (r.status === 404) {
        $("#library-title").textContent = `Manifest "${name}" not found`;
        return;
      }
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = await r.json();
      $("#library-title").textContent = body.source?.parent_title || body.name;
      const stats = body.stats || {};
      $("#library-sub").textContent =
        `${stats.total_file_units || 0} file units · `
        + `${stats.successful_pdfs || 0} PDFs · `
        + `${fmtBytes(stats.total_size_bytes || 0)} · `
        + `generated ${fmtDate(body.generated_at)}`;
      currentUnits = body.file_units || [];
      renderUnits(currentUnits);
    } catch (e) {
      $("#library-title").textContent = `Couldn't load: ${e.message}`;
    }
  }

  function renderUnits(units) {
    const wrap = $("#library-units");
    wrap.innerHTML = "";
    if (!units.length) {
      wrap.innerHTML = `<li class="muted">No matches.</li>`;
      return;
    }
    for (const u of units) {
      const li = document.createElement("li");
      li.className = "unit-row";
      if (u.status !== "ok") li.classList.add("unit-row-degraded");
      const dateRange = (u.inclusive_start_year || u.inclusive_end_year)
        ? `${u.inclusive_start_year || ""}${u.inclusive_end_year && u.inclusive_end_year !== u.inclusive_start_year ? "–" + u.inclusive_end_year : ""}`
        : "";
      li.innerHTML = `
        <div class="unit-main">
          <span class="unit-title">${escapeHtml(u.title || "(untitled)")}</span>
          <span class="muted">NAID ${escapeHtml(u.naid || "?")}${dateRange ? " · " + escapeHtml(dateRange) : ""}</span>
        </div>
        <div class="unit-meta">
          <span>${u.page_count || 0} pages</span>
          <span>${fmtBytes(u.pdf_size_bytes || 0)}</span>
          <span class="badge">${escapeHtml(u.status || "?")}</span>
        </div>
      `;
      if (u.pdf_path && u.status === "ok") {
        li.classList.add("unit-row-clickable");
        li.addEventListener("click", () => openPdf(u));
      }
      wrap.appendChild(li);
    }
  }

  function openPdf(u) {
    const panel = $("#pdf-panel");
    $("#pdf-panel-title").textContent = u.title || u.naid;
    // The pdf_path is stored as "pdfs/0001-..pdf"; strip the "pdfs/" prefix
    // because our static mount IS /pdfs.
    let path = u.pdf_path.replace(/^pdfs\//, "");
    $("#pdf-frame").src = `/pdfs/${path}#view=FitH`;
    panel.hidden = false;
  }

  function closePdf() {
    const panel = $("#pdf-panel");
    if (!panel) return;
    panel.hidden = true;
    $("#pdf-frame").src = "about:blank";
  }

  function applySearch(q) {
    if (!q.trim()) {
      renderUnits(currentUnits);
      return;
    }
    const pat = new RegExp(q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "i");
    renderUnits(
      currentUnits.filter(
        (u) => pat.test(u.title || "") || pat.test(u.scope_and_content_note || ""),
      ),
    );
  }

  // ---- routing ----

  function syncToHash() {
    const { tab, name } = parseHash();
    if (tab !== "library") {
      closePdf();
      return;
    }
    if (name) {
      $("#library-list-view").hidden = true;
      $("#library-detail-view").hidden = false;
      if (name !== currentName) loadDetail(name);
    } else {
      $("#library-list-view").hidden = false;
      $("#library-detail-view").hidden = true;
      currentName = null;
      loadList();
    }
  }

  // ---- wiring ----

  document.addEventListener("DOMContentLoaded", () => {
    syncToHash();
    window.addEventListener("hashchange", syncToHash);

    $("#library-back").addEventListener("click", () => { location.hash = "#library"; });
    $("#pdf-panel-close").addEventListener("click", closePdf);
    $("#library-search").addEventListener("input", (e) => {
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => applySearch(e.target.value), 150);
    });
  });
})();
