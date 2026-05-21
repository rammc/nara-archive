// First-run wizard. Validates the API key against NARA, then persists config
// + redirects to the main UI on success. Vanilla, no framework.

(function () {
  const $ = (sel) => document.querySelector(sel);
  const apiKey = $("#api-key");
  const outDir = $("#output-dir");
  const ack = $("#ack-terms");
  const validateBtn = $("#validate-btn");
  const validateMsg = $("#validate-msg");
  const getStartedBtn = $("#get-started");
  const setupMsg = $("#setup-msg");

  let keyValidated = false;

  function refreshSubmittable() {
    getStartedBtn.disabled = !(keyValidated && ack.checked);
  }

  function setValidateState(state, message) {
    validateMsg.textContent = message;
    validateMsg.classList.remove("muted", "setup-ok", "setup-err");
    if (state === "ok") validateMsg.classList.add("setup-ok");
    else if (state === "err") validateMsg.classList.add("setup-err");
    else validateMsg.classList.add("muted");
  }

  apiKey.addEventListener("input", () => {
    keyValidated = false;
    setValidateState("idle", "Click \u201CCheck this key\u201D to test it.");
    refreshSubmittable();
  });

  ack.addEventListener("change", refreshSubmittable);

  validateBtn.addEventListener("click", async () => {
    const key = (apiKey.value || "").trim();
    if (!key) {
      setValidateState("err", "Paste your NARA key into the field above first.");
      return;
    }
    validateBtn.disabled = true;
    setValidateState("idle", "Asking NARA…");
    try {
      const r = await fetch("/api/setup/validate-key", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ api_key: key }),
      });
      const body = await r.json();
      if (body.valid) {
        keyValidated = true;
        setValidateState("ok", body.message || "Looks good — NARA accepted this key.");
      } else {
        keyValidated = false;
        setValidateState("err", body.message || "NARA didn't accept that key.");
      }
    } catch (e) {
      keyValidated = false;
      setValidateState("err", `Couldn't reach the actari server: ${e.message}`);
    } finally {
      validateBtn.disabled = false;
      refreshSubmittable();
    }
  });

  getStartedBtn.addEventListener("click", async () => {
    getStartedBtn.disabled = true;
    setupMsg.textContent = "Saving config…";
    try {
      const body = {
        api_key: apiKey.value.trim(),
        output_dir: (outDir.value || "").trim() || null,
        terms_acknowledged: ack.checked,
      };
      const r = await fetch("/api/setup/complete", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({ detail: r.statusText }));
        throw new Error(err.detail || `HTTP ${r.status}`);
      }
      const result = await r.json();
      setupMsg.textContent = result.used_keychain
        ? "Saved — your API key is now in macOS Keychain. Loading actari…"
        : `Saved to ${result.saved_to}. Loading actari…`;
      // Hand the main UI a one-shot flag so it can greet the user with a
      // "try a Discovery search" nudge instead of dropping them into a
      // blank Discovery tab. The flag is consumed on read in app.js.
      try {
        sessionStorage.setItem("actari.firstLaunch", "1");
      } catch (_) {
        /* private-mode browsers etc. — non-critical, the nudge just won't fire */
      }
      // Tiny delay so the success message has a moment on screen.
      setTimeout(() => {
        location.href = "/";
      }, 600);
    } catch (e) {
      setupMsg.textContent = `Could not save: ${e.message}`;
      getStartedBtn.disabled = false;
    }
  });
})();
