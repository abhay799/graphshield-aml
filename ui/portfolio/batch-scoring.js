(() => {
  "use strict";
  const FIELDS = Object.freeze([
    "transaction_id", "event_ts", "from_bank", "from_account", "to_bank",
    "to_account", "amount_paid", "amount_received", "payment_currency",
    "receiving_currency", "payment_format",
  ]);
  const MAX_BYTES = 256 * 1024;
  const MAX_ROWS = 100;
  const MAX_COLUMNS = 32;
  const MAX_CELL = 1024;
  const TEMPLATE = FIELDS.join(",") + "\r\n";

  function timestamp(text) {
    const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})?$/.exec(text);
    if (!match) throw new Error("Use YYYY-MM-DDTHH:mm:ss[.fraction] with optional Z or ±HH:mm (up to 6 fractional digits).");
    const [, yearText, monthText, dayText, hourText, minuteText, secondText, fraction = "", zone = "Z"] = match;
    const [year, month, day, hour, minute, second] =
      [yearText, monthText, dayText, hourText, minuteText, secondText].map(Number);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (year < 1 || month < 1 || month > 12 || day < 1 || day > days[month - 1] ||
        hour > 23 || minute > 59 || second > 59) throw new Error("Invalid calendar date or time.");
    let offset = 0;
    if (zone !== "Z") {
      const zh = Number(zone.slice(1, 3)), zm = Number(zone.slice(4, 6));
      if (zh > 23 || zm > 59) throw new Error("Invalid timezone offset.");
      offset = (zh * 60 + zm) * (zone[0] === "+" ? 1 : -1);
    }
    const date = new Date(0);
    date.setUTCFullYear(year, month - 1, day);
    date.setUTCHours(hour, minute, second, 0);
    return BigInt(date.getTime() - offset * 60000) * 1000n +
      BigInt(fraction.padEnd(6, "0"));
  }

  // Finite-state CSV scanner. Quotes, escaped quotes and embedded newlines are
  // processed before field trimming; no record is truncated to meet a limit.
  function records(text) {
    const result = [];
    let fields = [], field = "", state = "plain", significant = false, number = 1;
    function append(char) {
      field += char;
      if (field.length > MAX_CELL) throw new Error("Maximum 1024 characters per cell exceeded.");
    }
    function endField() {
      fields.push(field.trim());
      if (fields.length > MAX_COLUMNS) throw new Error("Maximum 32 columns exceeded.");
      field = ""; state = "plain";
    }
    function endRecord() {
      endField();
      if (significant) result.push({ cells: fields, record: number });
      if (result.length > MAX_ROWS + 1) throw new Error("Maximum 100 nonblank transaction records exceeded.");
      fields = []; significant = false; number++;
    }
    for (let i = 0; i < text.length; i++) {
      const char = text[i];
      if (state === "quoted") {
        if (char === '"') {
          if (text[i + 1] === '"') { append('"'); i++; } else state = "closed";
        } else append(char);
        continue;
      }
      if (char === ",") { significant = true; endField(); continue; }
      if (char === "\r" || char === "\n") {
        endRecord();
        if (char === "\r" && text[i + 1] === "\n") i++;
        continue;
      }
      if (state === "closed") {
        if (char !== " " && char !== "\t") throw new Error("Malformed quoting after closing quote.");
        append(char); continue;
      }
      if (char === '"') {
        if (field.trim()) throw new Error("Malformed quoting in unquoted field.");
        field = ""; state = "quoted"; significant = true; continue;
      }
      append(char);
      if (char.trim()) significant = true;
    }
    if (state === "quoted") throw new Error("Unterminated quoted field.");
    endRecord();
    return result;
  }

  function parse(input) {
    if (typeof input !== "string") throw new Error("CSV text is required.");
    if (new TextEncoder().encode(input).byteLength > MAX_BYTES) throw new Error("Maximum file size is 256 KiB.");
    const scanned = records(input.replace(/^\uFEFF/, ""));
    if (!scanned.length) throw new Error("CSV requires a header and transaction records.");
    const headers = scanned.shift().cells;
    if (headers.some(h => !h)) throw new Error("Empty header is not allowed.");
    if (new Set(headers).size !== headers.length) throw new Error("Duplicate header is not allowed.");
    const labels = new Set(["is_laundering", "label", "labels", "ground_truth", "target", "fraud_label", "is_fraud"]);
    if (headers.some(h => labels.has(h.toLowerCase()))) throw new Error("Runtime label/ground-truth columns are rejected.");
    const missing = FIELDS.filter(h => !headers.includes(h));
    if (missing.length) throw new Error("Missing required headers: " + missing.join(", "));
    const ignored = headers.filter(h => !FIELDS.includes(h));
    const rows = scanned.map(({ cells, record }) => {
      if (cells.length !== headers.length) throw new Error("Record " + record + ": inconsistent column count.");
      const payload = {};
      const errors = [];
      for (const name of FIELDS) {
        const value = cells[headers.indexOf(name)];
        payload[name] = value;
        if (!value) errors.push(name + ": required value is blank.");
        if (name === "amount_paid" || name === "amount_received") {
          if (!/^\d+(?:\.\d+)?$/.test(value) || !Number.isFinite(Number(value))) {
            errors.push(name + ": enter a finite nonnegative decimal number without symbols or grouping.");
          } else payload[name] = Number(value);
        }
      }
      let instant = null;
      try { instant = timestamp(payload.event_ts); } catch (error) { errors.push("event_ts: " + error.message); }
      return { record, payload, errors, instant, state: "Ready", result: null, error: "", attempted: false };
    });
    const counts = new Map();
    for (const row of rows) {
      const id = row.payload.transaction_id;
      if (id) counts.set(id, (counts.get(id) || 0) + 1);
    }
    for (const row of rows) {
      if ((counts.get(row.payload.transaction_id) || 0) > 1) {
        row.errors.push("Duplicate transaction IDs are rejected because the scoring endpoint is stateful and does not provide transaction-ID idempotency.");
      }
      if (row.errors.length) row.state = "Invalid";
    }
    let previous = null;
    const orderErrors = [];
    for (const row of rows.filter(r => !r.errors.length)) {
      if (previous && row.instant < previous.instant) {
        orderErrors.push("Records " + previous.record + " and " + row.record + " have decreasing UTC timestamps.");
      }
      previous = row;
    }
    return { rows, ignored, orderError: orderErrors.join(" ") };
  }

  async function readFile(file) {
    if (!file || !/\.csv$/i.test(file.name)) throw new Error("Choose a UTF-8 CSV file.");
    if (file.size > MAX_BYTES) throw new Error("Maximum file size is 256 KiB; file was not read.");
    const buffer = await file.arrayBuffer();
    if (buffer.byteLength > MAX_BYTES) throw new Error("Maximum file size is 256 KiB.");
    let text;
    try { text = new TextDecoder("utf-8", { fatal: true }).decode(buffer); }
    catch { throw new Error("Invalid UTF-8 CSV encoding."); }
    return parse(text);
  }

  function validResponse(data, id) {
    return data !== null && typeof data === "object" && !Array.isArray(data) &&
      data.transaction_id === id && ["raw_model_score", "calibrated_score"].every(name =>
        typeof data[name] === "number" && Number.isFinite(data[name]) && data[name] >= 0 && data[name] <= 1);
  }

  function createController(io) {
    let dataset = { rows: [], ignored: [], orderError: "" };
    let running = false, stopping = false, blocked = false, selected = null, api = "";
    const attemptedIds = new Set();
    const notify = () => io.notify?.();
    function snapshot() { return { ...dataset, running, stopping, blocked, selected, api }; }
    function load(data) {
      if (running) return false;
      dataset = data; selected = null; blocked = false;
      for (const row of dataset.rows) {
        if (attemptedIds.has(row.payload.transaction_id)) {
          row.errors.push("This transaction ID was already submitted in this page session; it cannot be resubmitted.");
          row.state = "Invalid";
        }
      }
      notify(); return true;
    }
    function select(index) {
      if (running || !dataset.rows[index] || dataset.rows[index].errors.length) return false;
      selected = index; notify(); return true;
    }
    function stop() { if (running) { stopping = true; notify(); } }
    function clear() { return load({ rows: [], ignored: [], orderError: "" }); }
    async function run(which, base) {
      if (running || blocked || dataset.orderError) return;
      const candidates = which === "selected" ? [dataset.rows[selected]] : dataset.rows;
      const queue = candidates.filter(row => row && !row.errors.length && !row.attempted)
        .map(row => ({ row, payload: Object.freeze({ ...row.payload }) }));
      if (!queue.length || !io.acquire()) return;
      running = true; stopping = false; api = base;
      let uncertain = false;
      for (const { row } of queue) row.state = "Queued";
      notify();
      try {
        for (const { row, payload } of queue) {
          if (stopping) break;
          row.state = "Submitting"; row.attempted = true;
          attemptedIds.add(payload.transaction_id); notify();
          try {
            const { response, data } = await io.request(base, payload);
            if (!response.ok) {
              row.state = "Failed";
              row.error = io.httpError ? io.httpError(response, data) :
                "HTTP " + response.status + ": " + (typeof data?.detail === "string" ? data.detail : "API request failed.");
              blocked = true; break;
            }
            if (!validResponse(data, payload.transaction_id)) {
              row.state = "Failed";
              row.error = "Unexpected API response: missing, invalid or mismatched transaction/score fields. No score displayed. Runtime state may already have changed.";
              blocked = true; break;
            }
            row.result = data; row.state = "Completed";
          } catch (error) {
            row.state = "Completion unknown"; uncertain = true; blocked = true;
            row.error = (error.name === "AbortError" ? "Request timed out after 25 seconds." : "Connection/transport failed.") +
              " The server may still complete scoring and update Redis runtime history. No retry was made. Remaining rows were not submitted. Reload only after checking backend completion; reload is not a rollback.";
            break;
          } finally { notify(); }
        }
      } finally {
        for (const { row } of queue) if (row.state === "Queued") row.state = "Not submitted";
        running = false;
        io.release(uncertain); notify();
      }
    }
    return Object.freeze({ snapshot, load, select, run, stop, clear });
  }

  function mount(io) {
    const section = document.getElementById("batch-scoring");
    if (!section) return null;
    const el = id => document.getElementById(id);
    let reading = false, generation = 0;
    const controller = createController({ ...io, notify: render });
    const escape = io.escapeHTML;
    function cell(value) { return "<td>" + escape(value) + "</td>"; }
    function resultCells(row) {
      if (!row.result) return Array(10).fill(cell("—")).join("");
      const data = row.result, history = data.account_history || {};
      const values = [
        String(data.raw_model_score), String(data.calibrated_score),
        io.historyValue(history.sender), io.historyValue(history.receiver),
        io.booleanValue(data.limited_signal), io.textValue(data.scoring_mode),
        io.textValue(data.boundary), io.booleanValue(data.runtime_state_updated),
        io.booleanValue(data.canonical_artifacts_modified), io.booleanValue(data.synthetic_research_demo_only),
      ];
      return values.map(cell).join("");
    }
    function render() {
      const focusedRow = document.activeElement?.dataset?.row;
      const state = controller.snapshot();
      const locked = io.busy(), rows = state.rows;
      const valid = rows.filter(row => !row.errors.length).length;
      el("batch-summary").textContent = rows.length + " total rows · " + valid +
        " valid · " + (rows.length - valid) + " invalid";
      el("batch-ignored").textContent = state.ignored.length ? "Ignored columns (never sent): " + state.ignored.join(", ") : "";
      el("batch-order-error").textContent = state.orderError;
      const done = rows.filter(row => row.state === "Completed").length;
      const failed = rows.filter(row => row.state === "Failed" || row.state === "Completion unknown").length;
      const waiting = rows.filter(row => !row.errors.length && !row.attempted).length;
      el("batch-progress").textContent = (state.running ? (state.stopping ? "Stopping after current request. " : "Scoring. ") : "") +
        done + " completed · " + failed + " failed/unknown · " + waiting + " not submitted" +
        (state.api ? " · Request API: " + state.api : "") +
        (state.blocked ? " · Queue stopped after failure; no automatic continuation." : "");
      el("batch-progress").setAttribute("aria-busy", String(state.running));
      el("batch-file").disabled = locked;
      el("batch-clear").disabled = locked || !rows.length && !reading;
      el("batch-all").disabled = locked || reading || state.blocked || !!state.orderError || !waiting;
      const selected = rows[state.selected];
      el("batch-selected").disabled = locked || reading || state.blocked || !!state.orderError ||
        !selected || selected.errors.length > 0 || selected.attempted;
      el("batch-stop").disabled = !state.running || state.stopping;
      el("batch-body").innerHTML = rows.map((row, index) => {
        const selection = '<input type="radio" name="batch-row" data-row="' + index +
          '" aria-label="Select record ' + row.record + '"' +
          (state.selected === index ? " checked" : "") +
          (locked || row.errors.length ? " disabled" : "") + ">";
        const preview = ["transaction_id", "event_ts", "from_bank", "from_account",
          "to_bank", "to_account", "amount_paid", "amount_received"].map(name => cell(row.payload[name])).join("");
        return "<tr>" + cell(row.record) + "<td>" + selection + "</td>" + preview +
          cell(row.errors.length ? row.errors.join(" ") : "Valid") + cell(row.state) +
          resultCells(row) + cell(row.error || "—") + "</tr>";
      }).join("");
      if (focusedRow !== undefined) {
        const input = document.querySelector('#batch-body [data-row="' + focusedRow + '"]');
        if (input && !input.disabled) input.focus();
      }
      if (selected) {
        el("batch-detail").innerHTML = selected.result ? io.renderScoringResult(selected.result) :
          "<p>" + escape(selected.error || selected.errors.join(" ") || "No result yet for record " + selected.record + ".") + "</p>";
      } else el("batch-detail").innerHTML = '<p class="empty">Select a valid row to inspect its result.</p>';
    }
    el("batch-file").addEventListener("change", async event => {
      if (io.busy()) return;
      const token = ++generation;
      controller.clear();
      reading = true; el("batch-parse-status").textContent = "Parsing CSV locally…"; render();
      try {
        const data = await readFile(event.target.files[0]);
        if (token !== generation) return;
        controller.load(data); el("batch-parse-status").textContent = "CSV parsed. Review validation before scoring.";
      } catch (error) {
        if (token === generation) el("batch-parse-status").textContent = "CSV rejected: " + error.message;
      } finally { if (token === generation) { reading = false; render(); } }
    });
    el("batch-body").addEventListener("change", event => {
      if (event.target.dataset.row !== undefined) controller.select(Number(event.target.dataset.row));
    });
    function start(which) {
      if (reading || io.busy()) return;
      let base;
      try { base = io.selectedApiBase(); }
      catch { el("batch-parse-status").textContent = "Invalid API URL. Enter a valid HTTP or HTTPS API base URL."; return; }
      controller.run(which, base);
    }
    el("batch-all").addEventListener("click", () => start("all"));
    el("batch-selected").addEventListener("click", () => start("selected"));
    el("batch-stop").addEventListener("click", controller.stop);
    el("batch-clear").addEventListener("click", () => {
      if (io.busy()) return;
      generation++; reading = false; controller.clear(); el("batch-file").value = "";
      el("batch-parse-status").textContent = "Dataset cleared from this page. Submitted transactions were not rolled back.";
    });
    el("batch-template").addEventListener("click", () => {
      const url = URL.createObjectURL(new Blob([TEMPLATE], { type: "text/csv;charset=utf-8" }));
      const link = document.createElement("a");
      link.href = url; link.download = "graphshield-synthetic-transactions-template.csv";
      link.click(); URL.revokeObjectURL(url);
    });
    function importCSVText(text) {
      if (io.busy() || reading) throw new Error("Scoring UI is busy.");
      generation++;
      const data = parse(text);
      if (!controller.load(data)) throw new Error("Could not load converted transactions.");
      el("batch-file").value = "";
      el("batch-parse-status").textContent =
        "Converted bank-statement transactions loaded. Review them before scoring.";
      render();
      return data;
    }
    render();
    return Object.freeze({ refresh: render, importCSVText });
  }

  globalThis.GraphShieldBatch = Object.freeze({ parse, readFile, createController, mount, template: TEMPLATE });
})();