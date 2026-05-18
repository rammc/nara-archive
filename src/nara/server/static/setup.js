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
    setValidateState("idle", "Click Validate to test the key.");
    refreshSubmittable();
  });

  ack.addEventListener("change", refreshSubmittable);

  validateBtn.addEventListener("click", async () => {
    const key = (apiKey.value || "").trim();
    if (!key) {
      setValidateState("err", "Paste a key first.");
      return;
    }
    validateBtn.disabled = true;
    setValidateState("idle", "Talking to NARA…");
    try {
      const r = await fetch("/api/setup/validate-key", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ api_key: key }),
      });
      const body = await r.json();
      if (body.valid) {
        keyValidated = true;
        setValidateState("ok", body.message || "Key validated.");
      } else {
        keyValidated = false;
        setValidateState("err", body.message || "Key rejected.");
      }
    } catch (e) {
      keyValidated = false;
      setValidateState("err", `Network error: ${e.message}`);
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
        ? "Saved — your API key is now in macOS Keychain."
        : `Saved to ${result.saved_to}.`;
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
