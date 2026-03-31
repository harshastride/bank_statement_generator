// ── Injected into PAGE main world ──────────────────────────────────
// Intercepts statement downloads from HDFC netbanking.
// Must handle: knbcfdh.js wrapper, ruxitagent (Dynatrace), Zone.js (Angular)

(function () {
  "use strict";

  let isIntercepting = false;
  // Match both async and sync download endpoints
  const MATCH_PATTERNS = ["statements/download", "sync-download"];

  console.log("[StatementGen] Injecting page-level interceptor...");

  // ── Strategy 1: Patch XMLHttpRequest at the deepest level ───────
  // knbcfdh.js wraps XHR but still calls the real .open/.send underneath

  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;

  XMLHttpRequest.prototype.open = function (method, url) {
    this.__sg_url = String(url);
    this.__sg_method = method;
    return origOpen.apply(this, arguments);
  };

  XMLHttpRequest.prototype.send = function (body) {
    if (this.__sg_url && MATCH_PATTERNS.some(p => this.__sg_url.includes(p)) && !isIntercepting) {
      console.log("[StatementGen] >>> XHR INTERCEPTED:", this.__sg_url);
      triggerIntercept(this.__sg_url);

      // Abort and fake success
      try { this.abort(); } catch (e) {}
      fakeXhrResponse(this);
      return;
    }
    return origSend.apply(this, arguments);
  };

  function fakeXhrResponse(xhr) {
    setTimeout(() => {
      try {
        Object.defineProperty(xhr, "readyState", { value: 4, writable: false, configurable: true });
        Object.defineProperty(xhr, "status", { value: 200, writable: false, configurable: true });
        Object.defineProperty(xhr, "statusText", { value: "OK", writable: false, configurable: true });
        Object.defineProperty(xhr, "responseText", { value: "", writable: false, configurable: true });
        Object.defineProperty(xhr, "response", { value: new ArrayBuffer(0), writable: false, configurable: true });
        xhr.dispatchEvent(new Event("readystatechange"));
        xhr.dispatchEvent(new Event("load"));
        xhr.dispatchEvent(new Event("loadend"));
      } catch (e) {
        console.log("[StatementGen] Fake response error (non-critical):", e.message);
      }
    }, 50);
  }

  // ── Strategy 2: Patch fetch ─────────────────────────────────────
  // Even if knbcfdh.js saved an early ref, we patch the global

  const origFetch = window.fetch;
  window.fetch = function (input, init) {
    let url = "";
    if (typeof input === "string") url = input;
    else if (input && input.url) url = input.url;
    else if (input instanceof URL) url = input.toString();

    if (MATCH_PATTERNS.some(p => url.includes(p)) && !isIntercepting) {
      console.log("[StatementGen] >>> Fetch INTERCEPTED:", url);
      triggerIntercept(url);
      return Promise.resolve(new Response(new ArrayBuffer(0), { status: 200 }));
    }
    return origFetch.apply(window, arguments);
  };

  // ── Strategy 3: Monitor <a> tag clicks for download triggers ────
  // HDFC creates a temporary <a> with download attribute pointing to a blob URL.
  // We intercept the click to block the original PDF and trigger our custom one.

  const origClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    if (this.download && this.href && !isIntercepting) {
      const href = this.href;
      if (href.startsWith("blob:") || MATCH_PATTERNS.some(p => href.includes(p))) {
        console.log("[StatementGen] >>> <a> download click intercepted:", href, "download:", this.download);
        triggerIntercept(href);
        // Revoke the blob URL to prevent the original PDF from downloading
        if (href.startsWith("blob:")) {
          try { URL.revokeObjectURL(href); } catch (e) {}
        }
        // Block the original download by NOT calling origClick
        return;
      }
    }
    return origClick.apply(this, arguments);
  };

  // ── Strategy 4: Monitor programmatic <a> element creation + click ──
  // Some flows create an <a>, set href+download, append to DOM, click(), then remove.
  // We also patch appendChild to catch dynamically added download anchors.

  const origAppendChild = Node.prototype.appendChild;
  Node.prototype.appendChild = function (child) {
    if (child && child.tagName === "A" && child.download && child.href && !isIntercepting) {
      const href = child.href;
      if (href.startsWith("blob:") || MATCH_PATTERNS.some(p => href.includes(p))) {
        console.log("[StatementGen] >>> <a> append intercepted:", href, "download:", child.download);
        triggerIntercept(href);
        if (href.startsWith("blob:")) {
          try { URL.revokeObjectURL(href); } catch (e) {}
        }
        // Don't append the download anchor — block the original
        return child;
      }
    }
    return origAppendChild.apply(this, arguments);
  };

  // ── Trigger ─────────────────────────────────────────────────────

  function triggerIntercept(url) {
    if (isIntercepting) return;
    isIntercepting = true;
    setTimeout(() => { isIntercepting = false; }, 5000);

    // Send event to content script
    window.dispatchEvent(new CustomEvent("__sg_intercepted", {
      detail: { url: url, timestamp: Date.now() }
    }));
  }

  console.log("[StatementGen] Page-level interceptor ACTIVE (XHR + fetch + anchor click + anchor append)");
})();
