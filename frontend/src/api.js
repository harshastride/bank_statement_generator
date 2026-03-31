const BASE = '/api';

// ══════════════════════════════════════════════════════════════════════════════
// DASHBOARD & BANKS
// ══════════════════════════════════════════════════════════════════════════════

export async function getDashboard() {
  const res = await fetch(`${BASE}/dashboard`);
  return res.json();
}

export async function listBanks() {
  const res = await fetch(`${BASE}/banks`);
  return res.json();
}

// ══════════════════════════════════════════════════════════════════════════════
// ACCOUNTS (hierarchical API)
// ══════════════════════════════════════════════════════════════════════════════

export async function getBankFields(bankId) {
  const res = await fetch(`${BASE}/banks/${bankId}/fields`);
  return res.json();
}

export async function listAccounts(bankId) {
  const res = await fetch(`${BASE}/banks/${bankId}/accounts`);
  return res.json();
}

export async function createAccount(bankId, accountData) {
  const res = await fetch(`${BASE}/banks/${bankId}/accounts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(accountData),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

export async function deleteAccount(bankId, slug) {
  const res = await fetch(`${BASE}/banks/${bankId}/accounts/${slug}`, { method: 'DELETE' });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

export async function getAccountData(bankId, slug) {
  const res = await fetch(`${BASE}/banks/${bankId}/accounts/${slug}/data`);
  return res.json();
}

export async function saveAccountData(bankId, slug, data) {
  const res = await fetch(`${BASE}/banks/${bankId}/accounts/${slug}/data`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

// ══════════════════════════════════════════════════════════════════════════════
// TRANSACTIONS
// ══════════════════════════════════════════════════════════════════════════════

export async function uploadTransactions(bankId, slug, file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/banks/${bankId}/accounts/${slug}/transactions`, {
    method: 'POST', body: form,
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

export async function getTransactions(bankId, slug) {
  const res = await fetch(`${BASE}/banks/${bankId}/accounts/${slug}/transactions`);
  return res.json();
}

export async function saveTransactions(bankId, slug, transactions) {
  const res = await fetch(`${BASE}/banks/${bankId}/accounts/${slug}/transactions/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transactions }),
  });
  return res.json();
}

export async function addTransactions(bankId, slug, transactions) {
  const res = await fetch(`${BASE}/banks/${bankId}/accounts/${slug}/transactions/add`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transactions }),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

export async function recalculateBalances(bankId, slug) {
  const res = await fetch(`${BASE}/banks/${bankId}/accounts/${slug}/transactions/recalculate`, {
    method: 'POST',
  });
  return res.json();
}

// ══════════════════════════════════════════════════════════════════════════════
// GENERATE & STATEMENTS
// ══════════════════════════════════════════════════════════════════════════════

export async function generatePdf(bankId, slug, { filename } = {}) {
  const body = {};
  if (filename) body.filename = filename;
  const res = await fetch(`${BASE}/banks/${bankId}/accounts/${slug}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

export async function generatePdfRange(bankId, slug, startDate, endDate, { filename } = {}) {
  const body = { start_date: startDate, end_date: endDate };
  if (filename) body.filename = filename;
  const res = await fetch(`${BASE}/banks/${bankId}/accounts/${slug}/generate-range`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

export async function listStatements(bankId, slug) {
  const res = await fetch(`${BASE}/banks/${bankId}/accounts/${slug}/statements`);
  return res.json();
}

export function statementHtmlUrl(bankId, slug, startDate, endDate) {
  let url = `${BASE}/banks/${bankId}/accounts/${slug}/statement-html`;
  const params = [];
  if (startDate) params.push(`start_date=${encodeURIComponent(startDate)}`);
  if (endDate) params.push(`end_date=${encodeURIComponent(endDate)}`);
  if (params.length) url += '?' + params.join('&');
  return url;
}

export function statementDownloadUrl(bankId, slug, filename) {
  return `${BASE}/banks/${bankId}/accounts/${slug}/statements/${filename}`;
}

// ══════════════════════════════════════════════════════════════════════════════
// BANK SETUP (New Bank onboarding)
// ══════════════════════════════════════════════════════════════════════════════

export async function analyzePdf(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${BASE}/analyze-pdf`, { method: 'POST', body: form });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

export async function buildTemplate(profile, bankName, bankId) {
  const res = await fetch(`${BASE}/build-template`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ profile, bank_name: bankName, bank_id: bankId }),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

export async function onboardBank(file, bankName, bankId) {
  const form = new FormData();
  form.append('file', file);
  const params = new URLSearchParams();
  if (bankName) params.append('bank_name', bankName);
  if (bankId) params.append('bank_id', bankId);
  const url = `${BASE}/banks/onboard${params.toString() ? '?' + params.toString() : ''}`;
  const res = await fetch(url, { method: 'POST', body: form });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

// ══════════════════════════════════════════════════════════════════════════════
// LEGACY (for chrome extension backward compat)
// ══════════════════════════════════════════════════════════════════════════════

export async function legacyGenerateRange(jobId, startDate, endDate) {
  const res = await fetch(`${BASE}/jobs/${jobId}/generate-range`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ start_date: startDate, end_date: endDate }),
  });
  if (!res.ok) throw new Error((await res.json()).detail);
  return res.json();
}

export function legacyDownloadUrl(jobId) {
  return `${BASE}/jobs/${jobId}/download`;
}
