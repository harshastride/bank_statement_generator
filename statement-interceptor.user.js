// ==UserScript==
// @name         StatementGen Interceptor
// @namespace    https://statementgen.local
// @version      1.0
// @description  Intercepts PDF download requests and generates custom statements via local StatementGen backend
// @match        https://*/*
// @run-at       document-start
// @grant        GM_xmlhttpRequest
// @grant        GM_addStyle
// @connect      localhost
// @connect      127.0.0.1
// ==/UserScript==

(function () {
  "use strict";

  // ╔══════════════════════════════════════════════════════════════════╗
  // ║  CONFIGURATION — Edit these values to match your setup          ║
  // ╚══════════════════════════════════════════════════════════════════╝

  const CONFIG = {
    // Your StatementGen backend URL
    BACKEND_URL: "http://localhost:8000",

    // The job_id that has your uploaded template + account data + transactions
    JOB_ID: "419674ad",

    // Substring or regex pattern to match in outgoing API URLs.
    // When an XHR/fetch request URL contains this string, it will be intercepted.
    // Examples: "/statement/download", "/api/v1/accounts/statement", "/download/pdf"
    INTERCEPT_URL_PATTERN: "/statement/download",

    // Parameter names the target website might use for dates in its API requests.
    // The script checks both request body (JSON) and URL query parameters.
    DATE_PARAM_NAMES: {
      start: ["start_date", "startDate", "from_date", "fromDate", "from", "startDt", "from_dt", "beginDate", "begin_date"],
      end: ["end_date", "endDate", "to_date", "toDate", "to", "endDt", "to_dt", "finishDate", "finish_date"],
    },

    // If true, the original download request is blocked (returns fake 200).
    // If false, both the original and custom PDF download proceed.
    BLOCK_ORIGINAL: true,

    // Set to true to see debug logs in the console
    DEBUG: true,
  };

  // ── Logging ──────────────────────────────────────────────────────

  function log(...args) {
    if (CONFIG.DEBUG) console.log("[StatementGen]", ...args);
  }

  // ── Toast Notification UI ────────────────────────────────────────

  let toastContainer = null;

  function ensureToastContainer() {
    if (toastContainer && document.body.contains(toastContainer)) return;
    if (!document.body) return;

    toastContainer = document.createElement("div");
    toastContainer.id = "sg-toast-container";
    document.body.appendChild(toastContainer);

    GM_addStyle(`
      #sg-toast-container {
        all: initial;
        position: fixed !important;
        bottom: 24px !important;
        right: 24px !important;
        z-index: 2147483647 !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        display: flex !important;
        flex-direction: column !important;
        gap: 8px !important;
        pointer-events: none !important;
      }
      .sg-toast {
        all: initial;
        display: flex !important;
        align-items: center !important;
        gap: 10px !important;
        padding: 12px 18px !important;
        border-radius: 10px !important;
        font-size: 13px !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        color: #fff !important;
        box-shadow: 0 8px 32px rgba(0,0,0,0.18) !important;
        pointer-events: auto !important;
        animation: sg-slide-in 0.3s ease-out !important;
        max-width: 380px !important;
        line-height: 1.4 !important;
      }
      .sg-toast--info { background: #2563eb !important; }
      .sg-toast--loading { background: #d97706 !important; }
      .sg-toast--success { background: #16a34a !important; }
      .sg-toast--error { background: #dc2626 !important; }
      .sg-toast .sg-spinner {
        width: 16px !important; height: 16px !important;
        border: 2px solid rgba(255,255,255,0.3) !important;
        border-top-color: #fff !important;
        border-radius: 50% !important;
        animation: sg-spin 0.8s linear infinite !important;
        flex-shrink: 0 !important;
      }
      @keyframes sg-spin { to { transform: rotate(360deg); } }
      @keyframes sg-slide-in { from { transform: translateX(100px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
    `);
  }

  function showToast(message, type = "info", duration = 0) {
    ensureToastContainer();
    if (!toastContainer) return null;

    // Remove previous toasts
    toastContainer.innerHTML = "";

    const toast = document.createElement("div");
    toast.className = `sg-toast sg-toast--${type}`;

    if (type === "loading") {
      toast.innerHTML = `<div class="sg-spinner"></div><span>${message}</span>`;
    } else {
      const icon = type === "success" ? "\u2713" : type === "error" ? "\u2717" : "\u26A1";
      toast.innerHTML = `<span style="font-size:16px;flex-shrink:0">${icon}</span><span>${message}</span>`;
    }

    toastContainer.appendChild(toast);

    if (duration > 0) {
      setTimeout(() => toast.remove(), duration);
    }

    return toast;
  }

  // ── Date Normalization ───────────────────────────────────────────

  function normalizeDateToDDMMYYYY(value) {
    if (!value) return null;

    const v = String(value).trim();

    // Already DD/MM/YYYY
    if (/^\d{2}\/\d{2}\/\d{4}$/.test(v)) return v;

    // DD/MM/YY
    if (/^\d{2}\/\d{2}\/\d{2}$/.test(v)) {
      const [d, m, y] = v.split("/");
      return `${d}/${m}/20${y}`;
    }

    // YYYY-MM-DD or YYYY-MM-DDT...
    if (/^\d{4}-\d{2}-\d{2}/.test(v)) {
      const [y, m, d] = v.substring(0, 10).split("-");
      return `${d}/${m}/${y}`;
    }

    // DD-MM-YYYY
    if (/^\d{2}-\d{2}-\d{4}$/.test(v)) {
      const [d, m, y] = v.split("-");
      return `${d}/${m}/${y}`;
    }

    // DD-MM-YY
    if (/^\d{2}-\d{2}-\d{2}$/.test(v)) {
      const [d, m, y] = v.split("-");
      return `${d}/${m}/20${y}`;
    }

    // Unix timestamp (milliseconds)
    const num = Number(v);
    if (!isNaN(num) && num > 1000000000000) {
      const dt = new Date(num);
      return `${String(dt.getDate()).padStart(2, "0")}/${String(dt.getMonth() + 1).padStart(2, "0")}/${dt.getFullYear()}`;
    }

    // Unix timestamp (seconds)
    if (!isNaN(num) && num > 1000000000 && num < 1000000000000) {
      const dt = new Date(num * 1000);
      return `${String(dt.getDate()).padStart(2, "0")}/${String(dt.getMonth() + 1).padStart(2, "0")}/${dt.getFullYear()}`;
    }

    log("Could not normalize date:", v);
    return null;
  }

  // ── Date Extraction from Request ─────────────────────────────────

  function extractDates(url, body, method) {
    let startDate = null;
    let endDate = null;

    // 1. Check URL query parameters
    try {
      const urlObj = new URL(url, window.location.origin);
      for (const [key, val] of urlObj.searchParams.entries()) {
        const keyLower = key.toLowerCase();
        if (!startDate && CONFIG.DATE_PARAM_NAMES.start.some((n) => n.toLowerCase() === keyLower)) {
          startDate = normalizeDateToDDMMYYYY(val);
        }
        if (!endDate && CONFIG.DATE_PARAM_NAMES.end.some((n) => n.toLowerCase() === keyLower)) {
          endDate = normalizeDateToDDMMYYYY(val);
        }
      }
    } catch (e) {
      log("URL parse error:", e);
    }

    // 2. Check request body (JSON)
    if (body && typeof body === "string") {
      try {
        const parsed = JSON.parse(body);
        searchObjectForDates(parsed);
      } catch (e) {
        // Not JSON, try URL-encoded
        try {
          const params = new URLSearchParams(body);
          for (const [key, val] of params.entries()) {
            checkKeyForDate(key, val);
          }
        } catch (e2) { /* ignore */ }
      }
    }

    // 3. Check FormData
    if (body && typeof body === "object" && body instanceof FormData) {
      for (const [key, val] of body.entries()) {
        checkKeyForDate(key, String(val));
      }
    }

    // 4. Check URLSearchParams body
    if (body && typeof body === "object" && body instanceof URLSearchParams) {
      for (const [key, val] of body.entries()) {
        checkKeyForDate(key, val);
      }
    }

    function checkKeyForDate(key, val) {
      const keyLower = key.toLowerCase();
      if (!startDate && CONFIG.DATE_PARAM_NAMES.start.some((n) => n.toLowerCase() === keyLower)) {
        startDate = normalizeDateToDDMMYYYY(val);
      }
      if (!endDate && CONFIG.DATE_PARAM_NAMES.end.some((n) => n.toLowerCase() === keyLower)) {
        endDate = normalizeDateToDDMMYYYY(val);
      }
    }

    function searchObjectForDates(obj) {
      if (!obj || typeof obj !== "object") return;
      for (const [key, val] of Object.entries(obj)) {
        if (typeof val === "string" || typeof val === "number") {
          checkKeyForDate(key, String(val));
        } else if (typeof val === "object" && val !== null && !Array.isArray(val)) {
          // One level deep recursion (for nested params like { variables: { startDate: ... } })
          for (const [k2, v2] of Object.entries(val)) {
            if (typeof v2 === "string" || typeof v2 === "number") {
              checkKeyForDate(k2, String(v2));
            }
          }
        }
      }
    }

    if (startDate && endDate) {
      log("Extracted dates:", startDate, "to", endDate);
      return { startDate, endDate };
    }

    // 5. Fallback: scan URL path for date-like patterns (YYYY-MM-DD)
    const dateMatches = url.match(/(\d{4}-\d{2}-\d{2})/g);
    if (dateMatches && dateMatches.length >= 2) {
      startDate = normalizeDateToDDMMYYYY(dateMatches[0]);
      endDate = normalizeDateToDDMMYYYY(dateMatches[1]);
      if (startDate && endDate) {
        log("Extracted dates from URL path:", startDate, "to", endDate);
        return { startDate, endDate };
      }
    }

    log("Could not extract dates from request. URL:", url, "Body:", body);
    return null;
  }

  // ── GM_xmlhttpRequest Promise Wrapper ────────────────────────────

  function gmFetch(options) {
    return new Promise((resolve, reject) => {
      GM_xmlhttpRequest({
        timeout: 120000,
        ...options,
        onload: resolve,
        onerror: (err) => reject(new Error(err.statusText || "Network error")),
        ontimeout: () => reject(new Error("Request timed out")),
      });
    });
  }

  // ── Main Handler ─────────────────────────────────────────────────

  let isProcessing = false;

  async function handleInterceptedRequest(startDate, endDate) {
    if (isProcessing) {
      log("Already processing a request, skipping duplicate");
      return;
    }
    isProcessing = true;

    try {
      showToast(`Intercepted: ${startDate} \u2192 ${endDate}`, "info", 2000);
      await new Promise((r) => setTimeout(r, 500));

      // Step 1: Generate PDF
      showToast("Generating PDF...", "loading");
      log("Calling generate-range:", startDate, endDate);

      const genRes = await gmFetch({
        method: "POST",
        url: `${CONFIG.BACKEND_URL}/api/jobs/${CONFIG.JOB_ID}/generate-range`,
        headers: { "Content-Type": "application/json" },
        data: JSON.stringify({ start_date: startDate, end_date: endDate }),
      });

      if (genRes.status !== 200) {
        let detail = "Unknown error";
        try {
          detail = JSON.parse(genRes.responseText).detail || genRes.responseText;
        } catch (e) {
          detail = genRes.responseText || genRes.statusText;
        }
        throw new Error(detail);
      }

      const genData = JSON.parse(genRes.responseText);
      log("Generated:", genData);

      // Step 2: Download PDF
      showToast(`Downloading PDF (${genData.filtered_transactions} transactions)...`, "loading");

      const dlRes = await gmFetch({
        method: "GET",
        url: `${CONFIG.BACKEND_URL}/api/jobs/${CONFIG.JOB_ID}/download`,
        responseType: "blob",
      });

      if (dlRes.status !== 200) {
        throw new Error("Download failed: " + dlRes.statusText);
      }

      // Step 3: Trigger browser download
      const blob = dlRes.response;
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `statement_${startDate.replace(/\//g, "-")}_to_${endDate.replace(/\//g, "-")}.pdf`;
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        a.remove();
        URL.revokeObjectURL(blobUrl);
      }, 1000);

      showToast(
        `Statement downloaded (${genData.filtered_transactions} of ${genData.total_transactions} transactions)`,
        "success",
        5000
      );
    } catch (err) {
      log("Error:", err);
      const msg = err.message || "Unknown error";
      if (msg.includes("NetworkError") || msg.includes("Network error")) {
        showToast("Backend not running. Start: python app.py", "error", 8000);
      } else {
        showToast(`Error: ${msg}`, "error", 8000);
      }
    } finally {
      isProcessing = false;
    }
  }

  // ── URL Matching ─────────────────────────────────────────────────

  function urlMatchesPattern(url) {
    if (!url) return false;
    const pattern = CONFIG.INTERCEPT_URL_PATTERN;
    if (pattern.startsWith("/") && pattern.endsWith("/")) {
      // Regex pattern
      try {
        return new RegExp(pattern.slice(1, -1)).test(url);
      } catch (e) {
        return false;
      }
    }
    // Substring match
    return url.includes(pattern);
  }

  // ── XMLHttpRequest Interceptor ───────────────────────────────────

  const OrigXHROpen = XMLHttpRequest.prototype.open;
  const OrigXHRSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url, ...rest) {
    this._sgMethod = method;
    this._sgUrl = String(url);
    return OrigXHROpen.call(this, method, url, ...rest);
  };

  XMLHttpRequest.prototype.send = function (body) {
    if (urlMatchesPattern(this._sgUrl)) {
      log("XHR intercepted:", this._sgMethod, this._sgUrl);

      const dates = extractDates(this._sgUrl, body, this._sgMethod);

      if (dates) {
        handleInterceptedRequest(dates.startDate, dates.endDate);

        if (CONFIG.BLOCK_ORIGINAL) {
          log("Blocking original XHR request");
          // Simulate a successful empty response
          Object.defineProperty(this, "status", { get: () => 200 });
          Object.defineProperty(this, "readyState", { get: () => 4 });
          Object.defineProperty(this, "responseText", { get: () => "{}" });
          Object.defineProperty(this, "response", { get: () => "{}" });
          setTimeout(() => {
            this.dispatchEvent(new Event("readystatechange"));
            this.dispatchEvent(new Event("load"));
            this.dispatchEvent(new Event("loadend"));
          }, 10);
          return;
        }
      } else {
        log("Could not extract dates, letting original request through");
      }
    }

    return OrigXHRSend.call(this, body);
  };

  // ── Fetch Interceptor ────────────────────────────────────────────

  const OrigFetch = window.fetch;

  window.fetch = function (input, init) {
    let url = "";
    let body = null;
    let method = "GET";

    if (typeof input === "string") {
      url = input;
    } else if (input instanceof Request) {
      url = input.url;
      method = input.method;
    }

    if (init) {
      method = init.method || method;
      body = init.body || null;
    }

    if (urlMatchesPattern(url)) {
      log("Fetch intercepted:", method, url);

      const dates = extractDates(url, body, method);

      if (dates) {
        handleInterceptedRequest(dates.startDate, dates.endDate);

        if (CONFIG.BLOCK_ORIGINAL) {
          log("Blocking original fetch request");
          return Promise.resolve(
            new Response(JSON.stringify({ status: "intercepted" }), {
              status: 200,
              headers: { "Content-Type": "application/json" },
            })
          );
        }
      } else {
        log("Could not extract dates, letting original fetch through");
      }
    }

    return OrigFetch.call(window, input, init);
  };

  // ── Startup ──────────────────────────────────────────────────────

  log("Interceptor active on", window.location.href);
  log("Watching for URLs matching:", CONFIG.INTERCEPT_URL_PATTERN);
  log("Using job_id:", CONFIG.JOB_ID);

})();
