// Minimal SPA shell: URL-hash routing across four tabs, no framework yet.
// Alpine.js and per-tab logic land with the Discovery/Downloads/Library patches.

const TABS = ["discovery", "downloads", "library", "settings"];
const DEFAULT_TAB = "discovery";

function activeTabFromHash() {
  const raw = (location.hash || "").replace(/^#/, "").split("/")[0];
  return TABS.includes(raw) ? raw : DEFAULT_TAB;
}

function showTab(name) {
  for (const t of TABS) {
    const panel = document.getElementById(t);
    const link = document.querySelector(`.tabs a[data-tab="${t}"]`);
    if (panel) panel.hidden = t !== name;
    if (link) link.classList.toggle("active", t === name);
  }
  document.title = `nara archive · ${name}`;
}

async function loadHealth() {
  try {
    const resp = await fetch("/api/health");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const j = await resp.json();
    document.getElementById("footer-version").textContent = "v" + j.version;
    document.getElementById("footer-server").textContent = location.host;
    document.getElementById("kv-server").textContent = location.host;
    document.getElementById("kv-version").textContent = "v" + j.version;
    document.getElementById("kv-apikey").textContent = j.has_api_key
      ? "configured"
      : "missing — run `nara init`";
    document.getElementById("kv-output").textContent = j.output_dir;
    document.getElementById("kv-terms").textContent = j.terms_acknowledged
      ? "yes"
      : "no — run `nara init`";
  } catch (e) {
    document.getElementById("kv-apikey").textContent = "health check failed: " + e.message;
  }
}

window.addEventListener("hashchange", () => showTab(activeTabFromHash()));
window.addEventListener("DOMContentLoaded", () => {
  showTab(activeTabFromHash());
  loadHealth();
});
