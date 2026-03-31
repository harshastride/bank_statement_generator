const $ = (id) => document.getElementById(id);

let endpoints = [];

// ── Render endpoint list ─────────────────────────────────────────
function renderEndpoints() {
  const list = $("endpointList");
  if (endpoints.length === 0) {
    list.innerHTML = '<div class="endpoint-empty">No endpoints configured. Add URL patterns to intercept.</div>';
    return;
  }
  list.innerHTML = endpoints
    .map((ep, i) => {
      let domain = "";
      try {
        // Try to extract domain for display
        const cleaned = ep.replace(/\*/g, "").replace(/^https?:\/\//, "");
        domain = cleaned.split("/")[0];
      } catch (_) {}
      return `
        <div class="endpoint-item">
          <div>
            <span class="ep-url">${escapeHtml(ep)}</span>
            ${domain ? `<span class="ep-domain">${escapeHtml(domain)}</span>` : ""}
          </div>
          <button class="ep-remove" data-index="${i}" title="Remove">&times;</button>
        </div>`;
    })
    .join("");

  list.querySelectorAll(".ep-remove").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = parseInt(btn.dataset.index);
      endpoints.splice(idx, 1);
      renderEndpoints();
    });
  });
}

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

// ── Add endpoint ────────────────────────────────────────────────
$("addEndpointBtn").addEventListener("click", addEndpoint);
$("newEndpoint").addEventListener("keydown", (e) => {
  if (e.key === "Enter") addEndpoint();
});

function addEndpoint() {
  const input = $("newEndpoint");
  const val = input.value.trim();
  if (!val) return;
  if (endpoints.includes(val)) {
    showStatus("Endpoint already exists", "err");
    return;
  }
  endpoints.push(val);
  input.value = "";
  renderEndpoints();
}

// ── Load config on popup open ───────────────────────────────────
chrome.runtime.sendMessage({ type: "GET_CONFIG" }, (config) => {
  $("backendUrl").value = config.backendUrl || "https://bypass.skillxen.com";
  $("jobId").value = config.jobId || "";
  $("startDate").value = config.startDate || "";
  $("endDate").value = config.endDate || "";

  endpoints = config.interceptEndpoints || [
    "api-now.hdfc.bank.in/sync-download",
    "api-now.hdfc.bank.in/statements/download",
  ];
  renderEndpoints();

  const toggle = $("toggle-enabled");
  if (config.enabled) toggle.classList.add("active");
  toggle.addEventListener("click", () => {
    toggle.classList.toggle("active");
  });
});

// ── Save settings ───────────────────────────────────────────────
$("saveBtn").addEventListener("click", () => {
  const config = {
    backendUrl: $("backendUrl").value.replace(/\/$/, ""),
    jobId: $("jobId").value.trim(),
    enabled: $("toggle-enabled").classList.contains("active"),
    startDate: $("startDate").value || null,
    endDate: $("endDate").value || null,
    interceptEndpoints: endpoints,
  };

  chrome.runtime.sendMessage({ type: "SAVE_CONFIG", config }, () => {
    showStatus("Settings saved!", "ok");
  });
});

// ── Test generate ───────────────────────────────────────────────
$("testBtn").addEventListener("click", async () => {
  const backendUrl = $("backendUrl").value.replace(/\/$/, "");
  const jobId = $("jobId").value.trim();

  if (!jobId) {
    showStatus("Enter a Job ID first", "err");
    return;
  }

  let startDate = $("startDate").value;
  let endDate = $("endDate").value;

  if (!startDate || !endDate) {
    showStatus("Set start and end dates for manual test", "err");
    return;
  }

  startDate = formatDate(startDate);
  endDate = formatDate(endDate);

  showStatus("Generating...", "ok");

  try {
    const res = await fetch(`${backendUrl}/api/jobs/${jobId}/generate-range`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ start_date: startDate, end_date: endDate }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Failed");
    }

    const data = await res.json();

    chrome.downloads.download({
      url: `${backendUrl}/api/jobs/${jobId}/download`,
      filename: `statement_${startDate.replace(/\//g, "-")}_to_${endDate.replace(/\//g, "-")}.pdf`,
    });

    showStatus(
      `Downloaded! ${data.filtered_transactions} of ${data.total_transactions} transactions`,
      "ok"
    );
  } catch (err) {
    showStatus(`Error: ${err.message}`, "err");
  }
});

function formatDate(htmlDate) {
  if (!htmlDate) return "";
  const [y, m, d] = htmlDate.split("-");
  return `${d}/${m}/${y}`;
}

function showStatus(msg, type) {
  const el = $("status");
  el.textContent = msg;
  el.className = `status status-${type}`;
  el.style.display = "block";
  if (type === "ok") setTimeout(() => { el.style.display = "none"; }, 4000);
}
