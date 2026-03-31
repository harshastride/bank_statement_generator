// ── StatementGen Content Script ─────────────────────────────────────
// Runs in the ISOLATED content script world.
// 1. Injects interceptor into PAGE world (so it can patch XHR/fetch)
// 2. Listens for interception events from the page
// 3. Communicates with the background service worker

(function () {
  "use strict";

  // ── Step 1: Inject the interceptor script into the page's main world ──
  // Must run BEFORE the page's own scripts (knbcfdh.js, ruxitagent, etc.)

  const script = document.createElement("script");
  script.src = chrome.runtime.getURL("injected.js");
  // Prepend to <html> to run before any other scripts
  (document.documentElement || document.head).prepend(script);
  script.onload = function () { this.remove(); };

  console.log("[StatementGen] Content script loaded, injected page-level interceptor");

  // ── Step 2: Listen for interception events from injected.js ──

  window.addEventListener("__sg_intercepted", (e) => {
    console.log("[StatementGen] Received intercept event:", e.detail);

    // Try to extract dates from the intercepted URL first (sync-download has fromDate/toDate)
    let dates = extractDatesFromUrl(e.detail.url);

    // Fall back to extracting from page DOM
    if (!dates) dates = extractDatesFromPage();

    // Send to background service worker
    chrome.runtime.sendMessage({
      type: "INTERCEPT_DOWNLOAD",
      startDate: dates ? dates.startDate : null,
      endDate: dates ? dates.endDate : null,
      url: e.detail.url,
    });

    if (dates) {
      showToast(`Intercepted! ${dates.startDate} → ${dates.endDate}`, "info", 2000);
    } else {
      showToast("Intercepted! Using dates from extension settings.", "info", 2000);
    }
  });

  // ── Step 3: Listen for toast messages from background ──

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "TOAST") {
      const duration = msg.toastType === "success" ? 5000 : msg.toastType === "error" ? 8000 : 0;
      showToast(msg.message, msg.toastType, duration);
    }
  });

  // ── Date extraction from URL params ──────────────────────────────

  function extractDatesFromUrl(url) {
    if (!url) return null;
    try {
      const urlObj = new URL(url, window.location.origin);
      const paramNames = {
        start: ["fromDate", "from_date", "startDate", "start_date", "from"],
        end: ["toDate", "to_date", "endDate", "end_date", "to"],
      };

      let startDate = null;
      let endDate = null;

      for (const [key, val] of urlObj.searchParams.entries()) {
        if (!startDate && paramNames.start.some(n => n.toLowerCase() === key.toLowerCase())) {
          startDate = normalizeDateToDDMMYYYY(val);
        }
        if (!endDate && paramNames.end.some(n => n.toLowerCase() === key.toLowerCase())) {
          endDate = normalizeDateToDDMMYYYY(val);
        }
      }

      if (startDate && endDate) {
        console.log("[StatementGen] Extracted dates from URL:", startDate, "to", endDate);
        return { startDate, endDate };
      }
    } catch (e) {
      console.log("[StatementGen] URL parse error:", e);
    }
    return null;
  }

  // ── Date extraction from HDFC page DOM ──────────────────────────

  function extractDatesFromPage() {
    let startDate = null;
    let endDate = null;

    // HDFC has date inputs visible on the statement download page
    const allInputs = document.querySelectorAll("input");
    const datePattern = /^\d{2}-\d{2}-\d{4}$/;

    const dateValues = [];
    for (const inp of allInputs) {
      const val = inp.value.trim();
      if (datePattern.test(val)) {
        dateValues.push(val);
      }
    }

    // Also try DD/MM/YYYY format
    if (dateValues.length < 2) {
      const datePattern2 = /^\d{2}\/\d{2}\/\d{4}$/;
      for (const inp of allInputs) {
        const val = inp.value.trim();
        if (datePattern2.test(val) && !dateValues.includes(val)) {
          dateValues.push(val);
        }
      }
    }

    // Also try YYYY-MM-DD (HTML date input)
    if (dateValues.length < 2) {
      for (const inp of allInputs) {
        if (inp.type === "date" && inp.value) {
          dateValues.push(inp.value);
        }
      }
    }

    if (dateValues.length >= 2) {
      startDate = normalizeDateToDDMMYYYY(dateValues[0]);
      endDate = normalizeDateToDDMMYYYY(dateValues[1]);
      if (startDate && endDate) {
        console.log("[StatementGen] Extracted dates from page:", startDate, "to", endDate);
        return { startDate, endDate };
      }
    }

    console.log("[StatementGen] Could not extract dates from page. Found inputs:", dateValues);
    return null;
  }

  // ── Date normalization ──────────────────────────────────────────

  function normalizeDateToDDMMYYYY(value) {
    if (!value) return null;
    const v = String(value).trim();

    if (/^\d{2}\/\d{2}\/\d{4}$/.test(v)) return v;
    if (/^\d{2}\/\d{2}\/\d{2}$/.test(v)) {
      const [d, m, y] = v.split("/");
      return `${d}/${m}/20${y}`;
    }
    if (/^\d{4}-\d{2}-\d{2}/.test(v)) {
      const [y, m, d] = v.substring(0, 10).split("-");
      return `${d}/${m}/${y}`;
    }
    if (/^\d{2}-\d{2}-\d{4}$/.test(v)) {
      const [d, m, y] = v.split("-");
      return `${d}/${m}/${y}`;
    }
    if (/^\d{2}-\d{2}-\d{2}$/.test(v)) {
      const [d, m, y] = v.split("-");
      return `${d}/${m}/20${y}`;
    }
    return v;
  }

  // ── Toast UI ───────────────────────────────────────────────────

  function injectStyles() {
    if (document.getElementById("sg-styles")) return;
    const style = document.createElement("style");
    style.id = "sg-styles";
    style.textContent = `
      #sg-toast-container {
        position: fixed !important;
        bottom: 24px !important;
        right: 24px !important;
        z-index: 2147483647 !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        display: flex !important;
        flex-direction: column !important;
        gap: 8px !important;
      }
      .sg-toast {
        display: flex !important;
        align-items: center !important;
        gap: 10px !important;
        padding: 12px 18px !important;
        border-radius: 10px !important;
        font-size: 13px !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        color: #fff !important;
        box-shadow: 0 8px 32px rgba(0,0,0,0.18) !important;
        animation: sg-slide-in 0.3s ease-out !important;
        max-width: 400px !important;
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
    `;
    (document.head || document.documentElement).appendChild(style);
  }

  function showToast(message, type = "info", duration = 0) {
    injectStyles();
    let container = document.getElementById("sg-toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "sg-toast-container";
      document.body.appendChild(container);
    }
    container.innerHTML = "";

    const toast = document.createElement("div");
    toast.className = `sg-toast sg-toast--${type}`;
    if (type === "loading") {
      toast.innerHTML = `<div class="sg-spinner"></div><span>${message}</span>`;
    } else {
      const icon = type === "success" ? "\u2713" : type === "error" ? "\u2717" : "\u26A1";
      toast.innerHTML = `<span style="font-size:16px;flex-shrink:0">${icon}</span><span>${message}</span>`;
    }
    container.appendChild(toast);
    if (duration > 0) setTimeout(() => toast.remove(), duration);
  }

})();
