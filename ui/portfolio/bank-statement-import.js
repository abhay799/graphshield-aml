(() => {
  "use strict";

  const MAX_ROWS = 100;
  const HEADER_ALIASES = Object.freeze({
    date: ["transactiondate","txndate","date","valuedate","postingdate"],
    description: ["narration","description","particulars","remarks","transactiondetails","details"],
    debit: ["debit","withdrawal","withdrawalamount","debitamount","dr","withdrawals"],
    credit: ["credit","deposit","depositamount","creditamount","cr","deposits"],
    amount: ["amount","transactionamount","txnamount"],
    direction: ["type","drcr","debitcredit","direction"],
    reference: ["transactionid","txnid","reference","referenceno","refno","utr","utrno","chequeno"],
    mode: ["mode","transactiontype","channel","paymentmode"]
  });

  function cleanHeader(value) {
    return String(value ?? "").toLowerCase().replace(/[^a-z0-9]/g, "");
  }

  function findColumn(headers, aliases) {
    const normalized = headers.map(cleanHeader);
    const index = normalized.findIndex(name => aliases.includes(name));
    return index >= 0 ? headers[index] : null;
  }

  function detectMapping(headers) {
    const mapping = {};
    for (const [key, aliases] of Object.entries(HEADER_ALIASES)) {
      mapping[key] = findColumn(headers, aliases);
    }
    if (!mapping.date) throw new Error("Could not detect a transaction-date column.");
    if (!(mapping.debit || mapping.credit || mapping.amount)) {
      throw new Error("Could not detect debit/credit or amount columns.");
    }
    if (mapping.amount && !mapping.debit && !mapping.credit && !mapping.direction) {
      throw new Error("An amount-only statement also needs a debit/credit direction column.");
    }
    return mapping;
  }

  function numberValue(value) {
    if (value === null || value === undefined || value === "") return null;
    const cleaned = String(value).replace(/[₹,$£€\s]/g, "").replace(/,/g, "");
    if (!cleaned) return null;
    const parsed = Number(cleaned);
    return Number.isFinite(parsed) ? Math.abs(parsed) : null;
  }

  function parseDate(value) {
    if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
    if (typeof value === "number" && globalThis.XLSX?.SSF?.parse_date_code) {
      const d = XLSX.SSF.parse_date_code(value);
      if (d) return new Date(Date.UTC(d.y, d.m - 1, d.d, d.H || 0, d.M || 0, Math.floor(d.S || 0)));
    }
    const text = String(value ?? "").trim();
    if (!text) throw new Error("blank date");
    const m = /^(\d{1,2})[\/-](\d{1,2})[\/-](\d{2,4})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$/.exec(text);
    if (!m) {
      const iso = new Date(text);
      if (!Number.isNaN(iso.getTime())) return iso;
      throw new Error("unrecognized date");
    }
    let year = Number(m[3]);
    if (year < 100) year += 2000;
    const date = new Date(Date.UTC(year, Number(m[2]) - 1, Number(m[1]), Number(m[4] || 0), Number(m[5] || 0), Number(m[6] || 0)));
    if (Number.isNaN(date.getTime())) throw new Error("invalid date");
    return date;
  }

  function inferDirection(row, mapping) {
    const debit = mapping.debit ? numberValue(row[mapping.debit]) : null;
    const credit = mapping.credit ? numberValue(row[mapping.credit]) : null;
    if (debit && !credit) return { direction: "debit", amount: debit };
    if (credit && !debit) return { direction: "credit", amount: credit };
    if (mapping.amount) {
      const raw = row[mapping.amount];
      const amount = numberValue(raw);
      if (!amount) throw new Error("missing amount");
      const dir = String(mapping.direction ? row[mapping.direction] ?? "" : "").toLowerCase();
      if (/\b(dr|debit|withdrawal|withdraw)\b/.test(dir)) return { direction: "debit", amount };
      if (/\b(cr|credit|deposit)\b/.test(dir)) return { direction: "credit", amount };
      const signed = Number(String(raw).replace(/[₹,$£€\s,]/g, ""));
      if (Number.isFinite(signed) && signed < 0) return { direction: "debit", amount };
      throw new Error("amount direction is ambiguous");
    }
    throw new Error("missing amount");
  }

  function inferFormat(value, description) {
    const text = (String(value ?? "") + " " + String(description ?? "")).toUpperCase();
    if (text.includes("ACH")) return "ACH";
    if (/NEFT|RTGS|IMPS|UPI|TRANSFER|WIRE/.test(text)) return "Wire";
    if (/CARD|POS|VISA|MASTERCARD/.test(text)) return "Credit Card";
    if (/CHEQUE|CHECK/.test(text)) return "Cheque";
    if (/CASH|ATM/.test(text)) return "Cash";
    return "ACH";
  }

  async function token(text) {
    const source = String(text || "unknown").trim().toLowerCase();
    if (!crypto?.subtle) return "CP_" + Math.abs([...source].reduce((a,c) => ((a << 5) - a) + c.charCodeAt(0), 0));
    const bytes = new TextEncoder().encode(source);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    const hex = [...new Uint8Array(digest)].slice(0, 6).map(b => b.toString(16).padStart(2, "0")).join("");
    return "CP_" + hex;
  }

  function csvCell(value) {
    const text = String(value ?? "");
    return /[",\r\n]/.test(text) ? '"' + text.replaceAll('"', '""') + '"' : text;
  }

  async function convert(rows, mapping, options) {
    const owner = String(options.accountAlias || "MY_ACCOUNT").trim() || "MY_ACCOUNT";
    const bank = String(options.bankName || "MY_BANK").trim() || "MY_BANK";
    const currency = String(options.currency || "INR").trim().toUpperCase() || "INR";
    const converted = [];
    const errors = [];
    const seen = new Set();

    for (let i = 0; i < rows.length && converted.length < MAX_ROWS; i++) {
      const row = rows[i];
      try {
        const date = parseDate(row[mapping.date]);
        const { direction, amount } = inferDirection(row, mapping);
        const description = mapping.description ? row[mapping.description] : "";
        const counterparty = await token(description || (mapping.reference ? row[mapping.reference] : "unknown"));
        const rawReference = mapping.reference ? String(row[mapping.reference] ?? "").trim() : "";
        let transactionId = rawReference ? (await token(rawReference + "|" + (i + 1))).replace("CP_", "TX_") :
          "BANK_" + date.getTime() + "_" + (i + 1);
        if (seen.has(transactionId)) transactionId += "_" + (i + 1);
        seen.add(transactionId);
        const format = inferFormat(mapping.mode ? row[mapping.mode] : "", description);
        const fromAccount = direction === "debit" ? owner : counterparty;
        const toAccount = direction === "debit" ? counterparty : owner;
        const fromBank = direction === "debit" ? bank : "COUNTERPARTY_BANK";
        const toBank = direction === "debit" ? "COUNTERPARTY_BANK" : bank;

        converted.push({
          transaction_id: transactionId,
          event_ts: date.toISOString().replace(/\.\d{3}Z$/, "Z"),
          from_bank: fromBank,
          from_account: fromAccount,
          to_bank: toBank,
          to_account: toAccount,
          amount_paid: amount,
          amount_received: amount,
          payment_currency: currency,
          receiving_currency: currency,
          payment_format: format,
          _display_description: String(description || "").slice(0, 80),
          _direction: direction
        });
      } catch (error) {
        errors.push({ row: i + 2, message: error.message });
      }
    }

    converted.sort((a, b) => Date.parse(a.event_ts) - Date.parse(b.event_ts));
    return { converted, errors };
  }

  function toGraphShieldCSV(rows) {
    const fields = [
      "transaction_id","event_ts","from_bank","from_account","to_bank","to_account",
      "amount_paid","amount_received","payment_currency","receiving_currency","payment_format"
    ];
    return fields.join(",") + "\r\n" +
      rows.map(row => fields.map(name => csvCell(row[name])).join(",")).join("\r\n");
  }

  function matrixToObjects(matrix) {
    const aliases = new Set(Object.values(HEADER_ALIASES).flat());
    let bestIndex = -1, bestScore = -1;
    const limit = Math.min(matrix.length, 30);
    for (let i = 0; i < limit; i++) {
      const row = matrix[i] || [];
      const normalized = row.map(cleanHeader);
      const score = normalized.filter(value => aliases.has(value)).length;
      if (score > bestScore) { bestScore = score; bestIndex = i; }
    }
    if (bestIndex < 0 || bestScore < 2) {
      throw new Error("Could not find the transaction header row in the first 30 rows.");
    }
    const headers = matrix[bestIndex].map(v => String(v ?? "").trim());
    const rows = matrix.slice(bestIndex + 1)
      .filter(values => values.some(cell => String(cell ?? "").trim()))
      .map(values => Object.fromEntries(headers.map((h, i) => [h, values[i] ?? ""])));
    return { headers, rows, headerRow: bestIndex + 1 };
  }

  function parseCSV(text) {
    const lines = [];
    let row = [], field = "", quoted = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (quoted) {
        if (ch === '"' && text[i + 1] === '"') { field += '"'; i++; }
        else if (ch === '"') quoted = false;
        else field += ch;
      } else if (ch === '"') quoted = true;
      else if (ch === ",") { row.push(field); field = ""; }
      else if (ch === "\n" || ch === "\r") {
        if (ch === "\r" && text[i + 1] === "\n") i++;
        row.push(field); field = "";
        if (row.some(cell => String(cell).trim())) lines.push(row);
        row = [];
      } else field += ch;
    }
    row.push(field);
    if (row.some(cell => String(cell).trim())) lines.push(row);
    if (!lines.length) throw new Error("Statement is empty.");
    return matrixToObjects(lines);
  }

  async function readStatement(file) {
    if (!file) throw new Error("Choose a bank statement file.");
    const name = file.name.toLowerCase();
    if (file.size > 5 * 1024 * 1024) throw new Error("Maximum statement file size is 5 MiB.");
    if (name.endsWith(".csv")) {
      const text = await file.text();
      return parseCSV(text.replace(/^\uFEFF/, ""));
    }
    if (name.endsWith(".xlsx") || name.endsWith(".xls")) {
      if (!globalThis.XLSX) throw new Error("XLSX parser did not load. Refresh the page and try again.");
      const buffer = await file.arrayBuffer();
      const workbook = XLSX.read(buffer, { type: "array", cellDates: true });
      const firstSheet = workbook.Sheets[workbook.SheetNames[0]];
      const matrix = XLSX.utils.sheet_to_json(firstSheet, { header: 1, defval: "", raw: false });
      if (!matrix.length) throw new Error("No rows found in the first worksheet.");
      return matrixToObjects(matrix);
    }
    throw new Error("Use a CSV, XLSX, or XLS bank statement.");
  }

  function projectForLiveDemo(rows) {
    const projectedTs = new Date();
    projectedTs.setMilliseconds(0);
    const stamp = projectedTs.toISOString().replace(/\.\d{3}Z$/, "Z");
    const nonce = projectedTs.getTime().toString(36).toUpperCase();
    return rows.map((row, index) => ({
      ...row,
      transaction_id: row.transaction_id + "_D" + nonce + "_" + String(index + 1).padStart(3, "0"),
      event_ts: stamp
    }));
  }

  function renderPreview(rows) {
    const body = document.getElementById("statement-preview-body");
    body.innerHTML = rows.slice(0, 10).map(row =>
      "<tr><td>" + row.event_ts.replace("T", " ").replace("Z", "") + "</td>" +
      "<td>" + row._direction + "</td><td>" + row._display_description.replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c])) + "</td>" +
      "<td>" + row.amount_paid + "</td><td>" + row.payment_format + "</td>" +
      "<td>" + row.from_account + " → " + row.to_account + "</td></tr>"
    ).join("");
  }

  document.addEventListener("DOMContentLoaded", () => {
    const fileInput = document.getElementById("statement-file");
    if (!fileInput) return;
    const analyze = document.getElementById("statement-analyze");
    const load = document.getElementById("statement-load");
    const status = document.getElementById("statement-status");
    const mappingView = document.getElementById("statement-mapping");
    const preview = document.getElementById("statement-preview");
    let prepared = null;

    analyze.addEventListener("click", async () => {
      analyze.disabled = true;
      load.disabled = true;
      preview.hidden = true;
      status.textContent = "Reading statement locally in your browser…";
      try {
        const parsed = await readStatement(fileInput.files[0]);
        const mapping = detectMapping(parsed.headers);
        const result = await convert(parsed.rows, mapping, {
          bankName: document.getElementById("statement-bank").value,
          accountAlias: document.getElementById("statement-account-alias").value,
          currency: document.getElementById("statement-currency").value
        });
        if (!result.converted.length) throw new Error("No usable transactions could be converted.");
        prepared = result.converted;
        mappingView.textContent = "Header row " + parsed.headerRow + " · " +
          Object.entries(mapping).filter(([,v]) => v)
          .map(([k,v]) => k + " ← " + v).join(" · ");
        status.textContent = result.converted.length + " transactions converted locally" +
          (result.errors.length ? " · " + result.errors.length + " rows skipped" : "") +
          ". Counterparty identifiers are hashed before scoring.";
        renderPreview(prepared);
        preview.hidden = false;
        load.disabled = false;
      } catch (error) {
        prepared = null;
        status.textContent = "Could not import statement: " + error.message;
      } finally {
        analyze.disabled = false;
      }
    });

    load.addEventListener("click", () => {
      try {
        if (!prepared?.length) throw new Error("Analyze a statement first.");
        if (!globalThis.GraphShieldBatchUI?.importCSVText) throw new Error("Scoring table is not ready.");
        const projected = projectForLiveDemo(prepared);
        GraphShieldBatchUI.importCSVText(toGraphShieldCSV(projected));
        document.getElementById("batch-scoring").scrollIntoView({ behavior: "smooth", block: "start" });
        status.textContent = prepared.length +
          " transactions loaded as an explicit current-time demo projection. Original statement dates remain preview-only; this is not historical point-in-time scoring.";
      } catch (error) {
        status.textContent = "Could not load scoring table: " + error.message;
      }
    });
  });

  globalThis.GraphShieldStatementImport = Object.freeze({
    detectMapping, parseCSV, convert, toGraphShieldCSV, readStatement, projectForLiveDemo
  });
})();
