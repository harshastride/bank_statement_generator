// ── StatementGen Background Service Worker ─────────────────────────

const DEFAULT_CONFIG = {
  backendUrl: "https://bypass.skillxen.com",
  jobId: "419674ad",
  enabled: true,
  interceptEndpoints: [
    "api-now.hdfc.bank.in/sync-download",
    "api-now.hdfc.bank.in/statements/download",
  ],
};

async function getConfig() {
  const stored = await chrome.storage.local.get("config");
  return { ...DEFAULT_CONFIG, ...stored.config };
}

async function saveConfig(config) {
  await chrome.storage.local.set({ config });
}

function setBadge(text, color) {
  chrome.action.setBadgeText({ text });
  chrome.action.setBadgeBackgroundColor({ color });
  if (text) setTimeout(() => chrome.action.setBadgeText({ text: "" }), 5000);
}

// ── Build blocking rules from endpoint list ─────────────────────

function buildBlockRules(endpoints) {
  return endpoints.map((ep, i) => {
    // Extract domain and path from endpoint pattern
    const cleaned = ep.replace(/^https?:\/\//, "");
    const slashIdx = cleaned.indexOf("/");
    let domain, pathPattern;

    if (slashIdx >= 0) {
      domain = cleaned.substring(0, slashIdx);
      pathPattern = cleaned.substring(slashIdx);
    } else {
      domain = cleaned;
      pathPattern = "";
    }

    // Remove wildcard from domain if present
    domain = domain.replace(/\*/g, "").replace(/^\./, "");

    // Build regex: escape special chars, convert * to .*
    let regex = pathPattern
      ? ".*" + pathPattern.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*")
      : ".*";

    return {
      id: i + 1,
      priority: 1,
      action: { type: "block" },
      condition: {
        regexFilter: regex,
        requestDomains: domain ? [domain] : undefined,
        resourceTypes: ["xmlhttprequest", "other", "main_frame", "sub_frame"],
      },
    };
  });
}

async function enableBlocking() {
  try {
    const config = await getConfig();
    const rules = buildBlockRules(config.interceptEndpoints || []);

    // Remove all existing dynamic rules first
    const existing = await chrome.declarativeNetRequest.getDynamicRules();
    const existingIds = existing.map((r) => r.id);

    await chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds: existingIds,
      addRules: rules,
    });
    console.log("[StatementGen] Blocking ENABLED with", rules.length, "rules");
  } catch (e) {
    console.error("[StatementGen] Failed to enable blocking:", e);
  }
}

async function disableBlocking() {
  try {
    const existing = await chrome.declarativeNetRequest.getDynamicRules();
    const existingIds = existing.map((r) => r.id);
    await chrome.declarativeNetRequest.updateDynamicRules({
      removeRuleIds: existingIds,
    });
    console.log("[StatementGen] Blocking DISABLED");
  } catch (e) {
    console.error("[StatementGen] Failed to disable blocking:", e);
  }
}

// ── Date normalization ────────────────────────────────────────────

function normalizeDateToDDMMYYYY(value) {
  if (!value) return null;
  const v = String(value).trim();
  if (/^\d{2}\/\d{2}\/\d{4}$/.test(v)) return v;
  if (/^\d{2}\/\d{2}\/\d{2}$/.test(v)) { const [d,m,y]=v.split("/"); return `${d}/${m}/20${y}`; }
  if (/^\d{4}-\d{2}-\d{2}/.test(v)) { const [y,m,d]=v.substring(0,10).split("-"); return `${d}/${m}/${y}`; }
  if (/^\d{2}-\d{2}-\d{4}$/.test(v)) { const [d,m,y]=v.split("-"); return `${d}/${m}/${y}`; }
  if (/^\d{2}-\d{2}-\d{2}$/.test(v)) { const [d,m,y]=v.split("-"); return `${d}/${m}/20${y}`; }
  return v;
}

// ── Generate PDF and trigger download ─────────────────────────────

let isProcessing = false;

async function handleStatementDownload(startDate, endDate, tabId) {
  if (isProcessing) return;
  isProcessing = true;

  const config = await getConfig();
  if (!config.enabled) { isProcessing = false; return; }

  // Fall back to manual dates from config
  if ((!startDate || !endDate) && config.startDate && config.endDate) {
    const fmt = (d) => { const [y,m,dd]=d.split("-"); return `${dd}/${m}/${y}`; };
    startDate = fmt(config.startDate);
    endDate = fmt(config.endDate);
  }

  if (!startDate || !endDate) {
    setBadge("!", "#dc2626");
    sendToast(tabId, "Could not extract dates. Set them in the extension popup.", "error");
    isProcessing = false;
    return;
  }

  console.log("[StatementGen] Generating PDF:", startDate, "to", endDate);
  setBadge("...", "#d97706");
  sendToast(tabId, `Generating PDF: ${startDate} → ${endDate}`, "loading");

  try {
    const genRes = await fetch(
      `${config.backendUrl}/api/jobs/${config.jobId}/generate-range`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ start_date: startDate, end_date: endDate }),
      }
    );

    if (!genRes.ok) {
      const err = await genRes.json();
      throw new Error(err.detail || "Generation failed");
    }

    const genData = await genRes.json();
    console.log("[StatementGen] Generated:", genData);
    sendToast(tabId, `Downloading (${genData.filtered_transactions} txns)...`, "loading");

    const filename = `statement_${startDate.replace(/\//g,"-")}_to_${endDate.replace(/\//g,"-")}.pdf`;
    chrome.downloads.download({
      url: `${config.backendUrl}/api/jobs/${config.jobId}/download`,
      filename: filename,
      saveAs: false,
    });

    setBadge("OK", "#16a34a");
    sendToast(tabId, `Done! ${genData.filtered_transactions} of ${genData.total_transactions} transactions`, "success");
  } catch (err) {
    console.error("[StatementGen] Error:", err);
    setBadge("ERR", "#dc2626");
    if (err.message.includes("Failed to fetch")) {
      sendToast(tabId, "Backend not reachable. Check your backend URL.", "error");
    } else {
      sendToast(tabId, `Error: ${err.message}`, "error");
    }
  } finally {
    setTimeout(() => { isProcessing = false; }, 10000);
  }
}

function sendToast(tabId, message, toastType) {
  if (tabId && tabId > 0) {
    chrome.tabs.sendMessage(tabId, { type: "TOAST", message, toastType }).catch(() => {});
  }
}

// ── Message listener (from content script / injected.js) ──────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "INTERCEPT_DOWNLOAD") {
    console.log("[StatementGen] Intercept message received:", msg);
    handleStatementDownload(msg.startDate, msg.endDate, sender.tab?.id);
    sendResponse({ status: "ok" });
  }
  if (msg.type === "GET_CONFIG") {
    getConfig().then(sendResponse);
    return true;
  }
  if (msg.type === "SAVE_CONFIG") {
    saveConfig(msg.config).then(async () => {
      const cfg = { ...DEFAULT_CONFIG, ...msg.config };
      _cachedEnabled = cfg.enabled;
      _cachedEndpoints = cfg.interceptEndpoints || [];
      if (cfg.enabled) await enableBlocking();
      else await disableBlocking();
      sendResponse({ status: "saved" });
    });
    return true;
  }
});

// ── Auto-cancel & hide intercepted downloads ─────────────────────
// When declarativeNetRequest blocks a request, Chrome still creates a failed
// download entry visible in the download bar/history. We catch these and
// immediately cancel + erase them so the user never sees them.

let _cachedEnabled = true;
let _cachedEndpoints = DEFAULT_CONFIG.interceptEndpoints;

function matchesInterceptEndpoints(url, filename) {
  // Never touch our own downloads from the backend
  const backendUrl = DEFAULT_CONFIG.backendUrl;
  if (url.includes("localhost") || url.includes("127.0.0.1")) return false;
  if (backendUrl && url.includes(new URL(backendUrl).hostname)) return false;

  const combined = (url + " " + filename).toLowerCase();

  for (const ep of _cachedEndpoints) {
    const pattern = ep.toLowerCase().replace(/^https?:\/\//, "");
    // Split into parts by * for glob matching
    const parts = pattern.split("*").filter(Boolean);
    if (parts.length === 0) continue;
    if (parts.every((part) => combined.includes(part))) return true;
  }

  // Also check legacy patterns for HDFC blob downloads
  if (url.startsWith("blob:https://now.hdfc.bank.in")) return true;
  if (/Acct_Statement/i.test(filename)) return true;

  return false;
}

function cancelAndErase(downloadId) {
  try {
    chrome.downloads.cancel(downloadId, () => {
      chrome.downloads.erase({ id: downloadId });
    });
  } catch (e) {
    try { chrome.downloads.erase({ id: downloadId }); } catch (_) {}
  }
}

// Primary listener — fires the INSTANT a download is created.
chrome.downloads.onCreated.addListener((downloadItem) => {
  if (!_cachedEnabled) return;

  const filename = downloadItem.filename || downloadItem.finalUrl || "";
  const url = downloadItem.url || "";

  if (matchesInterceptEndpoints(url, filename)) {
    console.log("[StatementGen] Cancelling intercepted download:", downloadItem.id, filename || url);
    cancelAndErase(downloadItem.id);
  }
});

// Safety net — catches downloads whose state changes to interrupted/complete.
chrome.downloads.onChanged.addListener((delta) => {
  if (!_cachedEnabled) return;

  const dominated = delta.state || delta.filename;
  if (!dominated) return;

  chrome.downloads.search({ id: delta.id }, (items) => {
    if (!items || items.length === 0) return;
    const item = items[0];

    if (matchesInterceptEndpoints(item.url || "", item.filename || "")) {
      console.log("[StatementGen] Erasing intercepted download from history:", delta.id, item.filename);
      cancelAndErase(delta.id);
    }
  });
});

// ── Startup ───────────────────────────────────────────────────────

getConfig().then((cfg) => {
  _cachedEnabled = cfg.enabled;
  _cachedEndpoints = cfg.interceptEndpoints || DEFAULT_CONFIG.interceptEndpoints;
  if (cfg.enabled) enableBlocking();
});

console.log("[StatementGen] Background worker loaded");
