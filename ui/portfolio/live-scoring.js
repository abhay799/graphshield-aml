(() => {
  // Bound each request to 25 seconds. POST is never retried: a timed-out
  // request may still finish on the server and update Redis runtime history.
  const REQUEST_TIMEOUT_MS = 25000;
  const REQUEST_FIELDS = [
    "transaction_id", "event_ts", "from_bank", "from_account", "to_bank",
    "to_account", "amount_paid", "amount_received", "payment_currency",
    "receiving_currency", "payment_format",
  ];
  let scoringActive = false;
  let healthActive = false;
  let scoringUncertain = false;
  let batchUI = null;
  let previousManualResult = null;

  function syncScoringControls() {
    const locked = scoringActive || scoringUncertain;
    document.getElementById("score-submit").disabled = locked;
    document.getElementById("scoring-api-base").disabled = locked;
    batchUI?.refresh();
  }

  function acquireScoring() {
    if (scoringActive || scoringUncertain) return false;
    scoringActive = true;
    syncScoringControls();
    return true;
  }

  function releaseScoring(uncertain = false) {
    scoringActive = false;
    scoringUncertain = scoringUncertain || uncertain;
    syncScoringControls();
  }

  function isRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function escapeHTML(value) {
    return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }

  function textValue(value) {
    return typeof value === "string" && value.trim() ? value : "Unavailable";
  }

  function booleanValue(value) {
    return typeof value === "boolean" ? String(value) : "Unavailable";
  }

  function validScore(value) {
    return typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
  }

  function historyValue(value) {
    return value === "known" || value === "unknown" ? value : "Unavailable";
  }

  function metadataCard(label, value) {
    return '<div class="score-meta-card"><span>' + escapeHTML(label) +
      "</span><strong>" + escapeHTML(value) + "</strong></div>";
  }

  function scoringError(title, message) {
    return '<div class="scoring-error" role="alert"><strong>' + escapeHTML(title) +
      "</strong><p>" + escapeHTML(message) + "</p></div>";
  }

  function renderFeatureBreakdown(breakdown) {
    if (!isRecord(breakdown)) return '<p class="empty">Feature breakdown unavailable.</p>';
    const groups = ["transaction", "history", "network", "pass_through"];
    const rendered = groups.filter(name => isRecord(breakdown[name])).map(name => {
      const rows = Object.entries(breakdown[name]).map(([key, value]) => {
        // Preserve backend values; null is distinct from zero and absent data.
        const display = value === null ? "Null (missing)" :
          value === undefined ? "Unavailable" :
          typeof value === "object" ? JSON.stringify(value) : String(value);
        return '<div class="feature-row"><span>' + escapeHTML(key) +
          "</span><strong>" + escapeHTML(display) + "</strong></div>";
      }).join("");
      return '<details class="feature-group"' + (name === "history" ? " open" : "") +
        "><summary>" + escapeHTML(name.replaceAll("_", " ")) + "<span>" +
        Object.keys(breakdown[name]).length + ' features</span></summary><div class="feature-rows">' +
        (rows || '<p class="empty">No inputs returned in this group.</p>') + "</div></details>";
    }).join("");
    return rendered || '<p class="empty">Feature breakdown unavailable.</p>';
  }

  function renderStateJourney(data, payload) {
    const history = isRecord(data.account_history) ? data.account_history : {};
    const sender = historyValue(history.sender);
    const receiver = historyValue(history.receiver);
    const warm = sender === "known" && receiver === "known";
    const cold = sender === "unknown" || receiver === "unknown";
    const samePair = previousManualResult && payload &&
      previousManualResult.from_account === payload.from_account &&
      previousManualResult.to_account === payload.to_account;

    let comparison = "";
    if (samePair && validScore(previousManualResult.calibrated_score) &&
        validScore(data.calibrated_score)) {
      const delta = data.calibrated_score - previousManualResult.calibrated_score;
      comparison = '<div class="state-score-compare"><span>Previous calibrated score</span><strong>' +
        escapeHTML(previousManualResult.calibrated_score) + '</strong><span>Current calibrated score</span><strong>' +
        escapeHTML(data.calibrated_score) + '</strong><span>Change</span><strong>' +
        escapeHTML((delta >= 0 ? "+" : "") + delta.toFixed(6)) + '</strong></div>';
    }

    if (warm) {
      return '<div class="state-journey state-journey-warm">' +
        '<div class="state-journey-step done"><span>1</span><div><strong>Prior state exists</strong>' +
        '<p>Both accounts had Redis history before this transaction was scored.</p></div></div>' +
        '<div class="state-journey-step done"><span>2</span><div><strong>Warm-state scoring</strong>' +
        '<p>History-aware features were available for this request.</p></div></div>' +
        comparison +
        '<p class="state-journey-note">The score difference is a model-output change, not a fraud verdict or causal explanation.</p>' +
        '</div>';
    }
    if (cold) {
      return '<div class="state-journey state-journey-cold">' +
        '<div class="state-journey-step done"><span>1</span><div><strong>Cold-start transaction scored</strong>' +
        '<p>At least one account had no prior Redis history before scoring.</p></div></div>' +
        '<div class="state-journey-step"><span>2</span><div><strong>Build warm state</strong>' +
        '<p>Submit one more transaction with the same sender and receiver to see history-aware scoring.</p></div></div>' +
        '<button id="prepare-warm-followup" class="button scoring-followup" type="button">Prepare warm-state follow-up</button>' +
        '</div>';
    }
    return "";
  }

  function renderScoringResult(data, payload = null) {
    // Core scoring fields must be valid before showing a result. Optional
    // metadata remains visible as Unavailable when absent or malformed.
    if (!isRecord(data) || typeof data.transaction_id !== "string" || !data.transaction_id.trim() ||
        !validScore(data.calibrated_score) || !validScore(data.raw_model_score)) {
      return scoringError("Unexpected API response",
        "The API returned missing or invalid transaction/score fields. No score can be displayed.");
    }

    const history = isRecord(data.account_history) ? data.account_history : {};
    const sender = historyValue(history.sender);
    const receiver = historyValue(history.receiver);
    const warm = sender === "known" && receiver === "known";
    const cold = sender === "unknown" || receiver === "unknown";
    const context = warm ? "Warm-state context" :
      cold ? "Limited-history / cold-start context" : "Account-history context: Unavailable";
    const signalClass = warm ? "signal-warm" : cold ? "signal-limited" : "signal-neutral";

    return '<div class="score-result-header"><div><span class="ui-label">Calibrated research score</span>' +
      '<div class="score-value">' + escapeHTML(data.calibrated_score) + "</div>" +
      '<div class="score-percent">' + (data.calibrated_score * 100).toFixed(4) +
      '% (formatted calibrated score)</div></div></div>' +
      '<p class="signal-flag ' + signalClass + '">' + context + "</p>" +
      '<p class="scoring-help">UI explanation derived from account_history; not a separate backend field.</p>' +
      renderStateJourney(data, payload) +
      '<div class="score-meta-grid">' +
      metadataCard("transaction_id", data.transaction_id) +
      metadataCard("raw_model_score", String(data.raw_model_score)) +
      metadataCard("Sender history", sender) + metadataCard("Receiver history", receiver) +
      metadataCard("limited_signal", booleanValue(data.limited_signal)) +
      metadataCard("runtime_state_updated", booleanValue(data.runtime_state_updated)) + "</div>" +
      (data.limited_signal === true ?
        '<div class="limited-signal-warning"><strong>limitation_note</strong><p>' +
        escapeHTML(textValue(data.limitation_note)) + "</p></div>" : "") +
      '<div class="research-boundary"><h3>Backend safety / boundary metadata</h3>' +
      '<div class="score-meta-grid">' +
      metadataCard("scoring_mode", textValue(data.scoring_mode)) +
      metadataCard("boundary", textValue(data.boundary)) +
      metadataCard("synthetic_research_demo_only", booleanValue(data.synthetic_research_demo_only)) +
      metadataCard("canonical_artifacts_modified", booleanValue(data.canonical_artifacts_modified)) +
      '</div><p><strong>boundary_note:</strong> ' + escapeHTML(textValue(data.boundary_note)) +
      "</p></div>" +
      '<div class="feature-breakdown"><h3>Feature breakdown</h3>' +
      '<p class="scoring-help">Backend model inputs used for this scoring request.</p>' +
      '<p class="scoring-help">Read-only input inspection; these values do not explain causality.</p>' +
      renderFeatureBreakdown(data.feature_breakdown) + "</div>";
  }

  function httpError(response, data) {
    if (response.status === 409) {
      return scoringError(
        "Live-state timestamp conflict (HTTP 409)",
        "This timestamp is older than the live state's current time. Use the current time."
      );
    }
    if (response.status === 422 && typeof data?.detail === "string" &&
        data.detail.includes("more than 5 minutes ahead")) {
      return scoringError(
        "Timestamp too far in the future (HTTP 422)",
        "This timestamp is more than 5 minutes ahead of server time. Use the current time."
      );
    }
    if (response.status === 422) {
      const details = Array.isArray(data?.detail) ? data.detail : [];
      const messages = details.filter(isRecord).map(item => {
        const field = Array.isArray(item.loc) ?
          item.loc.filter(part => part !== "body").map(String).join(".") : "Request";
        return (field || "Request") + ": " + textValue(item.msg);
      });
      return scoringError("Request validation failed (HTTP 422)",
        messages.length ? messages.join("\n") : textValue(data?.detail));
    }
    if (response.status === 400) {
      return scoringError("Scoring request rejected (HTTP 400)", textValue(data?.detail));
    }
    if (response.status >= 500) {
      return scoringError("Server/scoring failure (HTTP " + response.status + ")",
        "The server could not complete this request. It was not automatically retried.");
    }
    return scoringError("API request failed (HTTP " + response.status + ")", textValue(data?.detail));
  }

  function requestError(error, scoring) {
    if (error.name === "AbortError") {
      return scoringError("Request timed out",
        "No response received within 25 seconds. The request was not retried." +
        (scoring ? " The server may still complete scoring and update Redis runtime history." : ""));
    }
    if (error.name === "NetworkError") {
      return scoringError("Connection failed",
        "Confirm the API URL, ensure the backend is running, and ensure the browser origin is allowed by GS_ALLOWED_ORIGINS.");
    }
    return scoringError("Request failed", "An unexpected error prevented this request from completing.");
  }

  function selectedApiBase() {
    const base = document.getElementById("scoring-api-base").value.trim().replace(/\/+$/, "");
    const url = new URL(base);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password ||
        url.search || url.hash) {
      throw new Error("Enter an HTTP or HTTPS API base URL without credentials, query, or fragment.");
    }
    return base;
  }

  async function requestJSON(url, options) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      let response;
      try {
        response = await fetch(url, { ...options, signal: controller.signal });
      } catch (error) {
        if (error.name === "AbortError") throw error;
        const networkError = new Error("Connection failed");
        networkError.name = "NetworkError";
        throw networkError;
      }
      let data;
      try {
        data = await response.json();
      } catch (error) {
        if (error.name === "AbortError") throw error;
        if (error instanceof TypeError) {
          const networkError = new Error("Response connection failed");
          networkError.name = "NetworkError";
          throw networkError;
        }
        data = null;
      }
      return { response, data };
    } finally {
      clearTimeout(timeout);
    }
  }

  function prepareWarmFollowup() {
    const transactionId = document.getElementById("score-transaction-id");
    const eventTs = document.getElementById("score-event-ts");
    if (transactionId) transactionId.value = "DEMO_WARM_" + Date.now();
    if (eventTs) eventTs.value = new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
    const submit = document.getElementById("score-submit");
    if (submit) {
      submit.textContent = "Score warm-state follow-up";
      submit.focus?.();
    }
  }

  async function scoreResearchTransaction(event) {
    event.preventDefault();
    if (scoringActive) return;
    if (scoringUncertain) return;
    const form = event.currentTarget;
    const result = document.getElementById("live-scoring-results");
    const submit = document.getElementById("score-submit");
    let base;
    try {
      base = selectedApiBase();
    } catch {
      result.innerHTML = scoringError("Invalid API URL", "Enter a valid HTTP or HTTPS API base URL.");
      return;
    }
    const values = new FormData(form);
    const payload = {};
    for (const field of REQUEST_FIELDS) {
      const value = values.get(field);
      payload[field] = field === "amount_paid" || field === "amount_received" ?
        (typeof value === "string" && value.trim() ? Number(value) : null) :
        (typeof value === "string" ? value.trim() : "");
    }

    if (!acquireScoring()) return;
    result.setAttribute("aria-busy", "true");
    result.innerHTML = '<p class="loading">Scoring synthetic transaction…</p>';
    submit.disabled = true;
    submit.textContent = "Scoring…";
    try {
      const { response, data } = await requestJSON(base + "/score/transaction", {
        method: "POST",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (response.ok) {
        result.innerHTML = renderScoringResult(data, payload);
        if (isRecord(data) && typeof data.transaction_id === "string" &&
            validScore(data.calibrated_score) && validScore(data.raw_model_score)) {
          const followup = document.getElementById("prepare-warm-followup");
          if (followup) followup.addEventListener("click", prepareWarmFollowup);
          previousManualResult = {
            from_account: payload.from_account,
            to_account: payload.to_account,
            calibrated_score: data.calibrated_score,
          };
        }
      } else {
        result.innerHTML = httpError(response, data);
      }
      result.innerHTML += '<p class="scoring-help">Request API: ' + escapeHTML(base) + "</p>";
    } catch (error) {
      result.innerHTML = requestError(error, true);
    } finally {
      releaseScoring();
      result.setAttribute("aria-busy", "false");
      submit.disabled = false;
      submit.textContent = "Score research transaction";
    }
  }

  async function checkScoringHealth() {
    if (healthActive) return;
    const result = document.getElementById("scoring-health-results");
    const button = document.getElementById("scoring-health-check");
    let base;
    try {
      base = selectedApiBase();
    } catch {
      result.innerHTML = scoringError("Invalid API URL", "Enter a valid HTTP or HTTPS API base URL.");
      return;
    }
    healthActive = true;
    button.disabled = true;
    result.setAttribute("aria-busy", "true");
    result.innerHTML = '<p class="loading">Checking selected API health…</p>';
    try {
      const { response, data } = await requestJSON(base + "/health", {
        method: "GET", headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        result.innerHTML = httpError(response, data);
      } else if (!isRecord(data)) {
        result.innerHTML = scoringError("Unexpected API response", "Health metadata unavailable.");
      } else {
        const fields = ["status", "service", "mode", "champion", "phase_1_6_artifacts",
          "scoring_mode", "scoring_state", "synthetic_research_demo_only"];
        result.innerHTML = '<p class="scoring-help">Health response from ' + escapeHTML(base) +
          '</p><div class="score-meta-grid">' + fields.map(field =>
            metadataCard(field, field === "synthetic_research_demo_only" ?
              booleanValue(data[field]) : textValue(data[field]))).join("") + "</div>";
      }
    } catch (error) {
      result.innerHTML = requestError(error, false);
    } finally {
      healthActive = false;
      result.setAttribute("aria-busy", "false");
      button.disabled = false;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("live-scoring-form");
    if (!form) return;

    const currentIso = () => new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
    const now = new Date();
    const transactionId = document.getElementById("score-transaction-id");
    const eventTs = document.getElementById("score-event-ts");
    const useNow = document.getElementById("score-event-ts-now");
    if (transactionId && !transactionId.value.trim()) {
      transactionId.value = "DEMO_LIVE_" + now.getTime();
    }
    if (eventTs && !eventTs.value.trim()) {
      eventTs.value = currentIso();
    }
    if (useNow && eventTs) {
      useNow.addEventListener("click", () => {
        eventTs.value = currentIso();
      });
    }
    if (typeof GraphShieldBatch !== "undefined") {
      batchUI = GraphShieldBatch.mount({
        acquire: acquireScoring, release: releaseScoring,
        busy: () => scoringActive || scoringUncertain,
        selectedApiBase, escapeHTML, textValue, booleanValue, historyValue,
        renderScoringResult,
        httpError: (response, data) => {
          // Convert the existing readable HTTP presentation to plain row text.
          const container = document.createElement("div");
          container.innerHTML = httpError(response, data);
          return container.textContent;
        },
        request: (base, payload) => requestJSON(base + "/score/transaction", {
          method: "POST",
          headers: { Accept: "application/json", "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }),
      });
      globalThis.GraphShieldBatchUI = batchUI;
    }
    form.addEventListener("submit", scoreResearchTransaction);
    document.getElementById("scoring-health-check").addEventListener("click", checkScoringHealth);
    document.getElementById("scoring-api-base").addEventListener("input", () => {
      if (!healthActive) document.getElementById("scoring-health-results").innerHTML =
        '<p class="empty">API URL changed. Check health for the selected URL.</p>';
    });
  });
})();
