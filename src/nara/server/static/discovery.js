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
  const recordGroup = $("#record-group");
  const presetsList = $("#presets-list");
  const presetsSummary = $("#presets-summary");
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
    const rg = (recordGroup?.value || "").trim();
    if (rg) {
      for (const r of rg.split(/[,\s]+/).filter(Boolean)) {
        params.append("record_group", r);
      }
    }
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

  const DOWNLOADABILITY_LABEL = {
    has_scans: { text: "Has scans", cls: "badge-scans", title: "Has its own digital objects — downloadable." },
    has_children: { text: "Browse contents", cls: "badge-children", title: "Container record — likely has descendants with scans." },
    likely_empty: { text: "May be empty", cls: "badge-empty", title: "No scans and not a known container — may produce no PDF." },
  };

  function downloadabilityBadge(h) {
    const meta = DOWNLOADABILITY_LABEL[h.downloadability] || DOWNLOADABILITY_LABEL.likely_empty;
    return `<span class="badge ${meta.cls}" title="${escapeHtml(meta.title)}">${escapeHtml(meta.text)}</span>`;
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
    const rg = h.record_group_number
      ? `<span class="meta-rg" title="Record Group">RG ${escapeHtml(h.record_group_number)}</span>`
      : "";
    li.innerHTML = `
      ${thumb}
      <div class="card-body">
        <h3>${escapeHtml(h.title || "(untitled)")}</h3>
        <div class="meta">
          <span class="badge">${escapeHtml(h.level || "?")}</span>
          ${downloadabilityBadge(h)}
          ${dateBadge(h) ? `<span class="meta-date">${escapeHtml(dateBadge(h))}</span>` : ""}
          <span class="meta-objs">${h.digital_object_count} objects</span>
          ${rg}
          <span class="meta-naid">NAID ${escapeHtml(h.naid)}</span>
        </div>
        ${note}
        <div class="card-actions">
          <button type="button" data-action="view" data-naid="${escapeHtml(h.naid)}">View</button>
          <button type="button" data-action="download" data-naid="${escapeHtml(h.naid)}" data-title="${escapeHtml(h.title || "")}" data-obj-count="${h.digital_object_count}" data-downloadability="${escapeHtml(h.downloadability || "")}">Download</button>
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
      const [detailResp, childResp] = await Promise.all([
        fetch(`/api/records/${encodeURIComponent(naid)}`),
        fetch(`/api/records/${encodeURIComponent(naid)}/children?limit=1`),
      ]);
      if (!detailResp.ok) throw new Error(`HTTP ${detailResp.status}`);
      const body = await detailResp.json();
      const childCount = childResp.ok ? (await childResp.json()).total ?? 0 : 0;
      renderDetail(body, childCount);
    } catch (e) {
      modalBody.innerHTML = `<p class="error">Failed to load: ${escapeHtml(e.message)}</p>`;
    }
  }

  function renderDetail(d, childCount) {
    const note = d.record?.scopeAndContentNote || "";
    const objs = (d.digital_objects || []).slice(0, 12);
    const ownObjCount = (d.digital_objects || []).length;
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
    const childSummary =
      childCount > 0
        ? `<p class="muted">Has ${childCount.toLocaleString()} direct child record${childCount === 1 ? "" : "s"} in NARA's catalog.</p>`
        : `<p class="muted">No direct child records in NARA's catalog.</p>`;
    const downloadable = ownObjCount > 0 || childCount > 0;
    const downloadBtn = downloadable
      ? `<button type="button" data-action="modal-download" data-naid="${escapeHtml(d.naid)}" data-title="${escapeHtml(d.title || "")}" data-obj-count="${ownObjCount}" data-child-count="${childCount}">Download</button>`
      : `<button type="button" disabled title="No digital objects and no child records — nothing to download.">Download (unavailable)</button>`;
    modalBody.innerHTML = `
      <h2>${escapeHtml(d.title || "(untitled)")}</h2>
      <p class="meta-row">
        <span class="badge">${escapeHtml(d.level || "?")}</span>
        <span class="muted">NAID ${escapeHtml(d.naid)}</span>
      </p>
      ${note ? `<p>${escapeHtml(note)}</p>` : ""}
      ${childSummary}
      ${objList}
      <div class="card-actions">${downloadBtn}</div>
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
  if (recordGroup) recordGroup.addEventListener("change", () => runSearch(1));

  pagerPrev.addEventListener("click", () => runSearch(Math.max(1, state.page - 1)));
  pagerNext.addEventListener("click", () => runSearch(state.page + 1));

  list.addEventListener("click", (e) => {
    const t = e.target;
    if (!(t instanceof HTMLElement)) return;
    const action = t.dataset.action;
    const naid = t.dataset.naid;
    if (!action || !naid) return;
    if (action === "view") openDetail(naid);
    if (action === "download") {
      const objCount = parseInt(t.dataset.objCount || "0", 10);
      maybeOpenJobDialog(t, naid, t.dataset.title || "", objCount);
    }
  });

  modal.addEventListener("click", (e) => {
    const t = e.target;
    if (!(t instanceof HTMLElement)) return;
    if (t === modal || t.dataset.dismiss !== undefined) {
      modal.close();
      return;
    }
    // Download CTA inside the modal already has accurate child + obj counts.
    if (t.dataset.action === "modal-download" && t.dataset.naid) {
      modal.close();
      openJobDialog(t.dataset.naid, t.dataset.title || "");
    }
  });

  async function maybeOpenJobDialog(btn, naid, title, objCount) {
    // Fast path: record has its own digital objects — leaf-record fallback will produce a PDF.
    if (objCount > 0) {
      openJobDialog(naid, title);
      return;
    }
    // Slow path: probe NARA for children. Disable the button to debounce double-clicks.
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Checking…";
    try {
      const r = await fetch(
        `/api/records/${encodeURIComponent(naid)}/children?limit=1`,
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      if ((data.total ?? 0) === 0) {
        alert(
          `NAID ${naid} has no digital objects and no child records in NARA's catalog — nothing to download. ` +
            `Try a Series- or Record-Group-level record, or open "View" to inspect the hierarchy.`,
        );
        return;
      }
      openJobDialog(naid, title);
    } catch (err) {
      alert(`Could not check children for NAID ${naid}: ${err.message}`);
    } finally {
      btn.disabled = false;
      btn.textContent = original;
    }
  }

  // --- preset chips ---

  function applyPreset(preset) {
    const s = preset.search || {};
    qInput.value = s.q || "";
    // Reset filters first so chained applies behave predictably.
    for (const b of levelBoxes()) b.checked = false;
    hasDigital.checked = !!s.has_digital_objects;
    yearFrom.value = s.year_from != null ? String(s.year_from) : "";
    yearTo.value = s.year_to != null ? String(s.year_to) : "";
    if (recordGroup) recordGroup.value = (s.record_group || []).join(", ");
    for (const lvl of s.level || []) {
      const box = levelBoxes().find((b) => b.value === lvl);
      if (box) box.checked = true;
    }
    runSearch(1);
  }

  async function loadPresets() {
    if (!presetsList) return;
    try {
      const r = await fetch("/api/presets");
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = await r.json();
      renderPresets(body.presets || []);
    } catch (e) {
      presetsList.innerHTML = `<span class="error">Could not load presets: ${escapeHtml(e.message)}</span>`;
    }
  }

  function renderPresets(presets) {
    if (!presetsList) return;
    if (!presets.length) {
      presetsList.textContent = "No presets available.";
      return;
    }
    const byCategory = new Map();
    for (const p of presets) {
      const cat = p.category || "Other";
      if (!byCategory.has(cat)) byCategory.set(cat, []);
      byCategory.get(cat).push(p);
    }
    const groups = [];
    for (const [cat, items] of byCategory) {
      const chips = items
        .map(
          (p) => `<button type="button" class="preset-chip"
            data-preset-id="${escapeHtml(p.id)}"
            title="${escapeHtml(p.description || "")}">
            ${escapeHtml(p.title)}${p.direct_naid ? ` <span class="muted">· NAID ${escapeHtml(p.direct_naid)}</span>` : ""}
          </button>`,
        )
        .join("");
      groups.push(
        `<div class="preset-group"><h4>${escapeHtml(cat)}</h4><div class="preset-chips">${chips}</div></div>`,
      );
    }
    presetsList.classList.remove("muted");
    presetsList.innerHTML = groups.join("");
    if (presetsSummary) presetsSummary.textContent = `${presets.length} curated entry points`;

    // Stash for click handler.
    presetsList.__presets = presets;
  }

  if (presetsList) {
    presetsList.addEventListener("click", (e) => {
      const t = e.target;
      if (!(t instanceof HTMLElement)) return;
      const chip = t.closest(".preset-chip");
      if (!chip) return;
      const id = chip.getAttribute("data-preset-id");
      const presets = presetsList.__presets || [];
      const p = presets.find((x) => x.id === id);
      if (p) applyPreset(p);
    });
  }

  loadPresets();

  // --- job creation dialog ---

  const jobDialog = $("#job-dialog");
  const jobForm = $("#job-form");
  const jobNameInput = $("#job-name");
  const jobFilterInput = $("#job-filter");
  const jobRateInput = $("#job-rate");
  const jobSub = $("#job-dialog-sub");

  function slugifyClient(s) {
    return (s || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 30) || "job";
  }

  let pendingNaid = null;
  function openJobDialog(naid, title) {
    pendingNaid = naid;
    jobNameInput.value = slugifyClient(title) || `naid-${naid}`;
    jobFilterInput.value = "";
    jobRateInput.value = "0.5";
    jobSub.textContent = `Parent NAID ${naid}${title ? ` · ${title.slice(0, 80)}` : ""}`;
    jobDialog.showModal();
  }

  jobDialog.addEventListener("click", (e) => {
    const t = e.target;
    if (t instanceof HTMLElement && t.dataset.dismiss !== undefined) {
      jobDialog.close();
    }
  });

  jobForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!pendingNaid) return;
    const body = {
      parent_naid: pendingNaid,
      name: jobNameInput.value.trim(),
      filter_query: jobFilterInput.value.trim() || null,
      rate: parseFloat(jobRateInput.value) || 0.5,
    };
    try {
      const r = await fetch("/api/jobs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      jobDialog.close();
      // Switch to Downloads tab; downloads.js polls automatically.
      location.hash = "#downloads";
      if (window.__naraDownloads) window.__naraDownloads.refresh();
    } catch (err) {
      alert(`Could not create job: ${err.message}`);
    }
  });
})();
