// Settings tab: read /api/config (key always masked), PATCH non-secret
// fields, reveal the ~/.nara folder in the platform file manager.

(function () {
  const $ = (s) => document.querySelector(s);

  function setMsg(text, kind = "muted") {
    const el = $("#settings-msg");
    el.className = kind;
    el.textContent = text;
  }

  function render(cfg) {
    $("#kv-server").textContent = location.host;
    $("#kv-version").textContent = "—";  // filled from /api/health below
    const keychainBadge = cfg.keychain_active
      ? ' <span class="badge badge-scans" title="Stored in macOS Keychain">Keychain</span>'
      : "";
    $("#kv-apikey").innerHTML = cfg.has_api_key
      ? `configured (${escapeHtml(cfg.api_key_masked || "")})${keychainBadge}`
      : "missing — run <code>nara init</code> or visit /setup";
    $("#kv-apibase").textContent = cfg.api_base_url;
    $("#kv-output").textContent = cfg.output_dir;
    $("#kv-configpath").textContent = cfg.config_path || "(none — using env / .env)";
    $("#kv-terms").textContent = cfg.terms_acknowledged
      ? `yes${cfg.acknowledged_at ? ` (${cfg.acknowledged_at})` : ""}`
      : "no — run `nara init`";
    $("#set-rate").value = cfg.default_rate;
    $("#set-autobrowser").checked = !!cfg.auto_open_browser;
    const resetBtn = $("#settings-reset-key");
    if (resetBtn) resetBtn.hidden = !cfg.has_api_key;
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  async function refresh() {
    try {
      const [cfgResp, healthResp] = await Promise.all([
        fetch("/api/config"),
        fetch("/api/health"),
      ]);
      if (!cfgResp.ok) throw new Error(`config: HTTP ${cfgResp.status}`);
      render(await cfgResp.json());
      if (healthResp.ok) {
        const h = await healthResp.json();
        $("#kv-version").textContent = "v" + h.version;
        $("#footer-version").textContent = "v" + h.version;
        $("#footer-server").textContent = location.host;
      }
    } catch (e) {
      setMsg(`Failed to load: ${e.message}`, "error");
    }
  }

  async function save(e) {
    e.preventDefault();
    setMsg("Saving…");
    const body = {
      default_rate: parseFloat($("#set-rate").value),
      auto_open_browser: $("#set-autobrowser").checked,
    };
    try {
      const r = await fetch("/api/config", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      render(await r.json());
      setMsg("Saved.");
    } catch (e) {
      setMsg(`Save failed: ${e.message}`, "error");
    }
  }

  async function reveal() {
    setMsg("Opening folder…");
    try {
      const r = await fetch("/api/config/reveal", { method: "POST" });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      const { opened } = await r.json();
      setMsg(`Opened ${opened}`);
    } catch (e) {
      setMsg(`Reveal failed: ${e.message}`, "error");
    }
  }

  function activeTab() {
    return (location.hash || "").replace(/^#/, "").split("/")[0] || "discovery";
  }

  async function resetKey() {
    if (!confirm("Remove the stored API key and return to the setup wizard?")) return;
    setMsg("Resetting…");
    try {
      const r = await fetch("/api/config/reset-key", { method: "POST" });
      if (!r.ok && r.status !== 204) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      location.href = "/setup";
    } catch (e) {
      setMsg(`Reset failed: ${e.message}`, "error");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    refresh();
    window.addEventListener("hashchange", () => {
      if (activeTab() === "settings") refresh();
    });
    $("#settings-form").addEventListener("submit", save);
    $("#settings-reveal").addEventListener("click", reveal);
    const resetBtn = $("#settings-reset-key");
    if (resetBtn) resetBtn.addEventListener("click", resetKey);
  });
})();
