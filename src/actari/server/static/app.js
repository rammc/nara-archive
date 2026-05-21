// Minimal SPA shell: URL-hash routing across four tabs.
// Tab-specific logic lives in discovery.js / downloads.js / library.js /
// settings.js. The footer is populated by settings.js (which pulls /api/health).

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
  document.title = `actari archive · ${name}`;
}

window.addEventListener("hashchange", () => showTab(activeTabFromHash()));
window.addEventListener("DOMContentLoaded", () => {
  showTab(activeTabFromHash());
});
