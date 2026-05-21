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
  document.title = `actari · ${name}`;
}

// First-launch nudge: if the setup wizard just finished, it set a one-shot
// flag in sessionStorage. We consume it once, show the welcome banner, and
// wire the dismiss button. Anyone bookmarking a tab won't see this again.
function maybeShowFirstLaunchBanner() {
  let shouldShow = false;
  try {
    shouldShow = sessionStorage.getItem("actari.firstLaunch") === "1";
    if (shouldShow) sessionStorage.removeItem("actari.firstLaunch");
  } catch (_) {
    /* private mode or storage disabled — no banner, no harm */
  }
  const banner = document.getElementById("first-launch-banner");
  if (!banner) return;
  if (shouldShow) banner.hidden = false;
  const dismiss = document.getElementById("first-launch-dismiss");
  if (dismiss) {
    dismiss.addEventListener("click", () => {
      banner.hidden = true;
    });
  }
}

window.addEventListener("hashchange", () => showTab(activeTabFromHash()));
window.addEventListener("DOMContentLoaded", () => {
  showTab(activeTabFromHash());
  maybeShowFirstLaunchBanner();
});
