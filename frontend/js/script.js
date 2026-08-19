(() => {
  "use strict";

  // Backend base URL, set in js/config.js (window.API_BASE_URL).
  // Falls back to same-origin (empty string) if config.js wasn't loaded.
  const API_BASE = (window.API_BASE_URL || "").replace(/\/$/, "");

  // ---------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------
  const state = {
    emails: [],           // current inbox list (previews)
    fullBodies: {},        // id -> body text (for connected/pasted emails)
    activeId: null,
    totalTimeSavedSeconds: 0,
    source: "demo",
  };

  // ---------------------------------------------------------------------
  // DOM refs
  // ---------------------------------------------------------------------
  const $ = (id) => document.getElementById(id);

  const els = {
    apiStatusPill: $("apiStatusPill"),
    apiStatusText: $("apiStatusText"),
    tsValue: $("tsValue"),

    tryDemoBtn: $("tryDemoBtn"),
    pasteOwnBtn: $("pasteOwnBtn"),

    sourceTabs: document.querySelectorAll(".source-tab"),
    pastePanel: $("pastePanel"),
    connectPanel: $("connectPanel"),

    pasteForm: $("pasteForm"),
    pasteSender: $("pasteSender"),
    pasteSubject: $("pasteSubject"),
    pasteBody: $("pasteBody"),
    pasteAnalyzeBtn: $("pasteAnalyzeBtn"),

    connectForm: $("connectForm"),
    connectProvider: $("connectProvider"),
    connectEmail: $("connectEmail"),
    connectPassword: $("connectPassword"),
    connectBtn: $("connectBtn"),
    connectHint: $("connectHint"),

    inboxItems: $("inboxItems"),
    inboxCount: $("inboxCount"),

    emptyState: $("emptyState"),
    loadingState: $("loadingState"),
    loadingText: $("loadingText"),
    errorState: $("errorState"),
    errorText: $("errorText"),
    resultCard: $("resultCard"),

    priorityStamp: $("priorityStamp"),
    categoryChip: $("categoryChip"),
    resultSubject: $("resultSubject"),
    resultSender: $("resultSender"),
    resultTldr: $("resultTldr"),
    resultSummary: $("resultSummary"),
    resultKeyPoints: $("resultKeyPoints"),
    resultActions: $("resultActions"),
    sentimentValue: $("sentimentValue"),
    sentimentReason: $("sentimentReason"),
    replyValue: $("replyValue"),
    vaderValue: $("vaderValue"),
    timeSavedValue: $("timeSavedValue"),
    resultMeta: $("resultMeta"),

    toast: $("toast"),
  };

  // ---------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------
  function showToast(message, isError = false) {
    els.toast.textContent = message;
    els.toast.classList.toggle("is-error", isError);
    els.toast.classList.add("show");
    clearTimeout(showToast._t);
    showToast._t = setTimeout(() => els.toast.classList.remove("show"), 3200);
  }

  function fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso.slice(0, 16);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  function setPane(view) {
    els.emptyState.hidden = view !== "empty";
    els.loadingState.hidden = view !== "loading";
    els.errorState.hidden = view !== "error";
    els.resultCard.hidden = view !== "result";
  }

  async function apiFetch(path, options) {
    const url = API_BASE + path;
    let res;
    try {
      res = await fetch(url, options);
    } catch (networkErr) {
      throw new Error(
        `Could not reach the backend at ${API_BASE || "(same origin)"}. ` +
        `Check that it's running and that js/config.js points to the right URL.`
      );
    }
    let data;
    try {
      data = await res.json();
    } catch {
      throw new Error("The server returned an unexpected response.");
    }
    if (!res.ok) {
      throw new Error(data.error || `Request failed (${res.status})`);
    }
    return data;
  }

  // ---------------------------------------------------------------------
  // Health check
  // ---------------------------------------------------------------------
  async function checkHealth() {
    try {
      const data = await apiFetch("/api/health");
      els.apiStatusPill.classList.toggle("online", data.ai_configured);
      els.apiStatusPill.classList.toggle("offline", !data.ai_configured);
      els.apiStatusText.textContent = data.ai_configured
        ? "AI engine online"
        : "AI key missing — set GEMINI_API_KEY";
    } catch {
      els.apiStatusPill.classList.add("offline");
      els.apiStatusText.textContent = "Server unreachable";
    }
  }

  // ---------------------------------------------------------------------
  // Inbox rendering
  // ---------------------------------------------------------------------
  function renderInbox() {
    els.inboxItems.innerHTML = "";
    els.inboxCount.textContent = `${state.emails.length} message${state.emails.length === 1 ? "" : "s"}`;

    state.emails.forEach((e) => {
      const btn = document.createElement("button");
      btn.className = "inbox-item" + (e.id === state.activeId ? " active" : "");
      btn.setAttribute("data-id", e.id);
      btn.innerHTML = `
        <div class="ii-top">
          <span class="ii-sender">${escapeHtml(shortSender(e.sender))}</span>
          <span class="ii-date">${fmtDate(e.date)}</span>
        </div>
        <div class="ii-subject">${escapeHtml(e.subject)}</div>
        <div class="ii-preview">${escapeHtml(e.preview || "")}</div>
      `;
      btn.addEventListener("click", () => selectEmail(e.id));
      els.inboxItems.appendChild(btn);
    });
  }

  function shortSender(sender) {
    if (!sender) return "Unknown";
    const match = sender.match(/^(.*?)</);
    return match ? match[1].trim() : sender;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str ?? "";
    return div.innerHTML;
  }

  // ---------------------------------------------------------------------
  // Analysis flow
  // ---------------------------------------------------------------------
  async function selectEmail(id) {
    state.activeId = id;
    renderInbox();
    setPane("loading");
    els.loadingText.textContent = "Reading the email…";

    const emailMeta = state.emails.find((e) => e.id === id);
    const body = state.fullBodies[id];

    const payload = { id };
    if (body) {
      payload.body = body;
      payload.sender = emailMeta.sender;
      payload.subject = emailMeta.subject;
    }

    try {
      const result = await apiFetch("/api/summarize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      renderResult(result, emailMeta);
      accumulateTimeSaved(result.estimated_read_time_saved_seconds || 0);
    } catch (err) {
      setPane("error");
      els.errorText.textContent = err.message;
    }
  }

  function accumulateTimeSaved(seconds) {
    state.totalTimeSavedSeconds += seconds;
    els.tsValue.textContent = state.totalTimeSavedSeconds >= 60
      ? Math.round(state.totalTimeSavedSeconds / 60)
      : state.totalTimeSavedSeconds;
    document.querySelector(".ts-unit").textContent = state.totalTimeSavedSeconds >= 60 ? "m" : "s";
  }

  function renderResult(result, emailMeta) {
    setPane("result");

    const priority = (result.priority || "normal").toLowerCase();
    els.priorityStamp.textContent = priority;
    els.priorityStamp.className = "stamp stamp-" + priority;

    els.categoryChip.textContent = result.category || "General";
    els.resultSubject.textContent = emailMeta ? emailMeta.subject : (result.subject || "(no subject)");
    els.resultSender.textContent = emailMeta ? emailMeta.sender : "";

    els.resultTldr.textContent = result.tldr || "";
    els.resultSummary.textContent = result.summary || "";

    els.resultKeyPoints.innerHTML = "";
    (result.key_points || []).forEach((point) => {
      const li = document.createElement("li");
      li.textContent = point;
      els.resultKeyPoints.appendChild(li);
    });

    els.resultActions.innerHTML = "";
    const actions = result.action_items || [];
    if (actions.length === 0) {
      const li = document.createElement("li");
      li.className = "no-actions";
      li.textContent = "No action needed — informational only.";
      els.resultActions.appendChild(li);
    } else {
      actions.forEach((action, idx) => {
        const li = document.createElement("li");
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.id = `action-${idx}`;
        const span = document.createElement("span");
        span.textContent = action;
        li.appendChild(cb);
        li.appendChild(span);
        els.resultActions.appendChild(li);
      });
    }

    const sentiment = (result.sentiment || "neutral").toLowerCase();
    els.sentimentValue.innerHTML = `<span class="chip chip-sentiment-${sentiment}">${capitalize(sentiment)}</span>`;
    els.sentimentReason.textContent = result.sentiment_reason || "";

    els.replyValue.textContent = result.requires_reply ? "Yes" : "No";

    if (result.vader) {
      els.vaderValue.textContent = `${capitalize(result.vader.label)} (${result.vader.compound})`;
    } else {
      els.vaderValue.textContent = "—";
    }

    const saved = result.estimated_read_time_saved_seconds || 0;
    els.timeSavedValue.textContent = saved >= 60 ? `${Math.round(saved / 60)} min` : `${saved} sec`;

    const wc = result.original_word_count ?? "—";
    els.resultMeta.textContent = `Original: ~${wc} words · Analyzed in ${result.processing_time_ms ?? "—"} ms · Model: Gemini + VADER hybrid`;
  }

  function capitalize(s) {
    return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
  }

  // ---------------------------------------------------------------------
  // Demo inbox loading
  // ---------------------------------------------------------------------
  async function loadDemoInbox() {
    try {
      const data = await apiFetch("/api/demo-inbox");
      state.emails = data.emails;
      state.fullBodies = {};
      state.activeId = null;
      renderInbox();
      setPane("empty");
    } catch (err) {
      showToast(err.message, true);
    }
  }

  // ---------------------------------------------------------------------
  // Source tabs
  // ---------------------------------------------------------------------
  function switchSource(source) {
    state.source = source;
    els.sourceTabs.forEach((tab) => {
      const active = tab.dataset.source === source;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    els.pastePanel.hidden = source !== "paste";
    els.connectPanel.hidden = source !== "connect";

    if (source === "demo") loadDemoInbox();
  }

  els.sourceTabs.forEach((tab) => {
    tab.addEventListener("click", () => switchSource(tab.dataset.source));
  });

  els.tryDemoBtn.addEventListener("click", () => {
    switchSource("demo");
    document.querySelector(".dashboard").scrollIntoView({ behavior: "smooth", block: "start" });
  });

  els.pasteOwnBtn.addEventListener("click", () => {
    switchSource("paste");
    els.pastePanel.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  // ---------------------------------------------------------------------
  // Paste form
  // ---------------------------------------------------------------------
  els.pasteForm.addEventListener("submit", async (evt) => {
    evt.preventDefault();
    const body = els.pasteBody.value.trim();
    if (!body) return;

    const id = "pasted-" + Date.now();
    const sender = els.pasteSender.value.trim() || "Unknown sender";
    const subject = els.pasteSubject.value.trim() || "(no subject)";

    const preview = { id, sender, subject, date: new Date().toISOString(), preview: body.slice(0, 120) + "…" };
    state.emails = [preview, ...state.emails.filter((e) => !e.id.startsWith("pasted-"))];
    state.fullBodies[id] = body;
    renderInbox();

    els.pasteAnalyzeBtn.disabled = true;
    els.pasteAnalyzeBtn.textContent = "Analyzing…";
    try {
      await selectEmail(id);
      showToast("Email analyzed.");
      els.pasteForm.reset();
    } catch (err) {
      showToast(err.message, true);
    } finally {
      els.pasteAnalyzeBtn.disabled = false;
      els.pasteAnalyzeBtn.textContent = "Analyze email";
    }
  });

  // ---------------------------------------------------------------------
  // Connect form (IMAP)
  // ---------------------------------------------------------------------
  els.connectForm.addEventListener("submit", async (evt) => {
    evt.preventDefault();
    els.connectBtn.disabled = true;
    els.connectBtn.textContent = "Connecting…";
    els.connectHint.textContent = "";
    els.connectHint.className = "form-hint";

    try {
      const data = await apiFetch("/api/connect-inbox", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider: els.connectProvider.value,
          email: els.connectEmail.value.trim(),
          app_password: els.connectPassword.value.trim(),
          limit: 10,
        }),
      });

      state.emails = data.emails.map(({ body, ...preview }) => preview);
      state.fullBodies = {};
      data.emails.forEach((e) => { state.fullBodies[e.id] = e.body; });
      state.activeId = null;
      renderInbox();
      setPane("empty");

      els.connectHint.textContent = `Connected — loaded ${data.emails.length} recent emails.`;
      els.connectHint.className = "form-hint is-success";
      showToast("Inbox connected successfully.");
    } catch (err) {
      els.connectHint.textContent = err.message;
      els.connectHint.className = "form-hint is-error";
    } finally {
      els.connectBtn.disabled = false;
      els.connectBtn.textContent = "Fetch recent emails";
    }
  });

  // ---------------------------------------------------------------------
  // Init
  // ---------------------------------------------------------------------
  checkHealth();
  loadDemoInbox();
})();
