// Discovery tab: NARA search + result cards + filters + pagination + detail modal.
// No framework — vanilla DOM. Alpine.js gets pulled in later if/when Downloads/Library
// reactive state grows past hand-wired event listeners.

(function () {
  const DEBOUNCE_MS = 300;
  const PAGE_SIZE = 25;

  const $ = (sel) => document.querySelector(sel);

  const form = $("#search-form");
  const qInput = $("#search-q");
  const status = $("#search-status");
  const list = $("#search-results");
  const pager = $("#search-pager");
  const pagerPrev = $("#pager-prev");
  const pagerNext = $("#pager-next");
  const pagerInfo = $("#pager-info");
  const yearFrom = $("#year-from");
  const yearTo = $("#year-to");
  const hasDigital = $("#has-digital");
  const levelBoxes = () =>
    Array.from(document.querySelectorAll('input[name="level"]'));
  const modal = $("#record-modal");
  const modalBody = $("#modal-body");

  let state = { page: 1, total: 0, lastParams: null };
  let debounceTimer = null;

  function levelsSelected() {
    return levelBoxes().filter((b) => b.checked).map((b) => b.value);
  }

  function gatherParams(page = 1) {
    const params = new URLSearchParams();
    const q = qInput.value.trim();
    if (!q) return null;
    params.set("q", q);
    params.set("page", page);
    params.set("page_size", PAGE_SIZE);
    for (const lvl of levelsSelected()) params.append("level", lvl);
    if (yearFrom.value) params.set("year_from", yearFrom.value);
    if (yearTo.value) params.set("year_to", yearTo.value);
    if (hasDigital.checked) params.set("has_digital_objects", "true");
    return params;
  }

  function setStatus(text, isError = false) {
    status.textContent = text;
    status.classList.toggle("error", isError);
  }

  function clearResults() {
    list.innerHTML = "";
    pager.hidden = true;
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function dateBadge(h) {
    const a = h.inclusive_start_year;
    const b = h.inclusive_end_year;
    if (a && b && a !== b) return `${a}–${b}`;
    if (a) return `${a}`;
    if (b) return `${b}`;
    return "";
  }

  function renderCard(h) {
    const li = document.createElement("li");
    li.className = "card";
    const note = h.scope_and_content_note
      ? `<p class="muted">${escapeHtml(
          h.scope_and_content_note.slice(0, 200),
        )}${h.scope_and_content_note.length > 200 ? "…" : ""}</p>`
      : "";
    const thumb = h.thumbnail_url
      ? `<img class="thumb" src="${escapeHtml(h.thumbnail_url)}" alt="" loading="lazy" referrerpolicy="no-referrer">`
      : `<div class="thumb thumb-empty" aria-hidden="true">∅</div>`;
    li.innerHTML = `
      ${thumb}
      <div class="card-body">
        <h3>${escapeHtml(h.title || "(untitled)")}</h3>
        <div class="meta">
          <span class="badge">${escapeHtml(h.level || "?")}</span>
          ${dateBadge(h) ? `<span class="meta-date">${escapeHtml(dateBadge(h))}</span>` : ""}
          <span class="meta-objs">${h.digital_object_count} objects</span>
          <span class="meta-naid">NAID ${escapeHtml(h.naid)}</span>
        </div>
        ${note}
        <div class="card-actions">
          <button type="button" data-action="view" data-naid="${escapeHtml(h.naid)}">View</button>
          <button type="button" data-action="download" data-naid="${escapeHtml(h.naid)}" disabled title="Jobs UI ships in the next patch">Download</button>
        </div>
      </div>
    `;
    return li;
  }

  function renderResults(payload) {
    clearResults();
    state.page = payload.page;
    state.total = payload.total;
    if (payload.hits.length === 0) {
      setStatus(`No matches for "${qInput.value.trim()}".`);
      return;
    }
    for (const h of payload.hits) list.appendChild(renderCard(h));
    setStatus(
      `Showing ${payload.hits.length} of ${payload.total.toLocaleString()} results.`,
    );
    const totalPages = Math.max(1, Math.ceil(payload.total / payload.page_size));
    pagerInfo.textContent = `page ${payload.page} of ${totalPages}`;
    pagerPrev.disabled = payload.page <= 1;
    pagerNext.disabled = payload.page >= totalPages;
    pager.hidden = false;
  }

  async function runSearch(page = 1) {
    const params = gatherParams(page);
    if (!params) {
      clearResults();
      setStatus("Type a query to begin.");
      return;
    }
    state.lastParams = params;
    setStatus("Searching NARA…");
    try {
      const resp = await fetch(`/api/search?${params}`);
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }
      renderResults(await resp.json());
    } catch (e) {
      clearResults();
      setStatus(`Search failed: ${e.message}`, true);
    }
  }

  function scheduleSearch() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => runSearch(1), DEBOUNCE_MS);
  }

  // --- detail modal ---

  async function openDetail(naid) {
    modal.showModal();
    modalBody.innerHTML = `<p class="muted">Loading record ${escapeHtml(naid)}…</p>`;
    try {
      const resp = await fetch(`/api/records/${encodeURIComponent(naid)}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const body = await resp.json();
      renderDetail(body);
    } catch (e) {
      modalBody.innerHTML = `<p class="error">Failed to load: ${escapeHtml(e.message)}</p>`;
    }
  }

  function renderDetail(d) {
    const note = d.record?.scopeAndContentNote || "";
    const objs = (d.digital_objects || []).slice(0, 12);
    const objList = objs.length
      ? `<h4>Digital objects (showing ${objs.length} of ${d.digital_objects.length})</h4>
         <ul class="obj-list">${objs
           .map(
             (o) => `<li>
               <a href="${escapeHtml(o.objectUrl || "#")}" target="_blank" rel="noopener">${escapeHtml(o.objectFilename || "?")}</a>
               <span class="muted">${escapeHtml(o.objectType || "")}</span>
             </li>`,
           )
           .join("")}</ul>`
      : `<p class="muted">No digital objects on this record.</p>`;
    modalBody.innerHTML = `
      <h2>${escapeHtml(d.title || "(untitled)")}</h2>
      <p class="meta-row">
        <span class="badge">${escapeHtml(d.level || "?")}</span>
        <span class="muted">NAID ${escapeHtml(d.naid)}</span>
      </p>
      ${note ? `<p>${escapeHtml(note)}</p>` : ""}
      ${objList}
    `;
  }

  // --- event wiring ---

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    clearTimeout(debounceTimer);
    runSearch(1);
  });

  qInput.addEventListener("input", scheduleSearch);
  for (const b of levelBoxes()) b.addEventListener("change", () => runSearch(1));
  hasDigital.addEventListener("change", () => runSearch(1));
  yearFrom.addEventListener("change", () => runSearch(1));
  yearTo.addEventListener("change", () => runSearch(1));

  pagerPrev.addEventListener("click", () => runSearch(Math.max(1, state.page - 1)));
  pagerNext.addEventListener("click", () => runSearch(state.page + 1));

  list.addEventListener("click", (e) => {
    const t = e.target;
    if (!(t instanceof HTMLElement)) return;
    const action = t.dataset.action;
    const naid = t.dataset.naid;
    if (!action || !naid) return;
    if (action === "view") openDetail(naid);
    // download triggers POST /api/jobs in the next patch
  });

  modal.addEventListener("click", (e) => {
    const t = e.target;
    if (t instanceof HTMLElement && (t === modal || t.dataset.dismiss !== undefined)) {
      modal.close();
    }
  });
})();
