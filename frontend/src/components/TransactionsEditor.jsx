import { useState, useEffect, useRef, useCallback } from 'react';
import { uploadTransactions, getTransactions, saveTransactions, addTransactions, recalculateBalances, getBankFields } from '../api';

const DEFAULT_COLUMNS = [
  { key: 'date',        label: 'Date',        type: 'date',   width: 'w-28' },
  { key: 'description', label: 'Description', type: 'text',   flex: true },
  { key: 'credit',      label: 'Credit',      type: 'amount', width: 'w-28', color: 'green' },
  { key: 'debit',       label: 'Debit',       type: 'amount', width: 'w-28', color: 'red' },
  { key: 'balance',     label: 'Balance',     type: 'amount', width: 'w-32', readonly: true },
];

function makeEmptyRow(columns) {
  const row = {};
  columns.forEach(c => { row[c.key] = ''; });
  return row;
}

function parseNum(v) {
  if (!v) return 0;
  const cleaned = String(v).replace(/,/g, '').replace(/"/g, '').trim();
  const n = parseFloat(cleaned);
  return isNaN(n) ? 0 : n;
}

function fmtBal(n) {
  return n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Parse DD/MM/YYYY or DD/MM/YY to a sortable number (YYYYMMDD)
function parseDateSort(d) {
  if (!d) return 0;
  const m = String(d).match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{2,4})$/);
  if (!m) return 0;
  const day = parseInt(m[1]);
  const mon = parseInt(m[2]);
  let yr = parseInt(m[3]);
  if (yr < 100) yr += 2000;
  return yr * 10000 + mon * 100 + day;
}

// Sort rows by date descending (newest first), stable within same date
function sortByDateDesc(rows) {
  return [...rows].sort((a, b) => {
    const da = parseDateSort(a.date);
    const db = parseDateSort(b.date);
    return db - da; // descending
  });
}

// Full recalc: compute opening balance from oldest row, then recalculate ALL rows
function fullRecalc(rows) {
  if (rows.length === 0) return rows;
  const chrono = [...rows].reverse(); // oldest first
  // Derive opening balance: oldest row's balance = opening + credit - debit
  // So opening = balance - credit + debit
  const oldest = chrono[0];
  const openingBal = Math.round((parseNum(oldest.balance) - parseNum(oldest.credit) + parseNum(oldest.debit)) * 100) / 100;
  // Recalculate ALL rows from opening balance
  let running = openingBal;
  const result = chrono.map(r => {
    running = Math.round((running + parseNum(r.credit) - parseNum(r.debit)) * 100) / 100;
    return { ...r, balance: fmtBal(running) };
  });
  return result.reverse(); // back to newest-first
}

function htmlDateToCsv(htmlDate) {
  if (!htmlDate) return '';
  const [y, m, d] = htmlDate.split('-');
  return `${d}/${m}/${y.slice(2)}`;
}

export default function TransactionsEditor({ bankId, accountSlug, onDone, onRowsChange }) {
  const [rows, setRows] = useState([]);
  const [columns, setColumns] = useState(DEFAULT_COLUMNS);
  const [bankFields, setBankFields] = useState(null);
  const [saving, setSaving] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [newTxns, setNewTxns] = useState([{}]);
  const [adding, setAdding] = useState(false);
  const [message, setMessage] = useState(null);
  const [search, setSearch] = useState('');
  const [dirty, setDirty] = useState(false);
  const [autoSaving, setAutoSaving] = useState(false);
  const [csvPromptCopied, setCsvPromptCopied] = useState(false);
  const [sortOrder, setSortOrder] = useState('desc'); // 'desc' (newest first) | 'asc'
  const [dragIdx, setDragIdx] = useState(null);
  const [dragOverIdx, setDragOverIdx] = useState(null);
  const rowsRef = useRef(rows);
  const dirtyRef = useRef(false);
  const saveTimerRef = useRef(null);

  const creditCol = columns.find(c => c.key === 'credit');
  const debitCol = columns.find(c => c.key === 'debit');

  useEffect(() => {
    rowsRef.current = rows;
    if (onRowsChange) onRowsChange(rows);
  }, [rows]);
  useEffect(() => { dirtyRef.current = dirty; }, [dirty]);

  useEffect(() => {
    getBankFields(bankId).then(data => {
      setBankFields(data);
      if (data.transactionColumns && data.transactionColumns.length > 0) {
        setColumns(data.transactionColumns);
      }
    });
    loadData();
  }, [bankId, accountSlug]);

  function scheduleAutoSave(updatedRows) {
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(async () => {
      setAutoSaving(true);
      await saveTransactions(bankId, accountSlug, updatedRows);
      setDirty(false);
      setAutoSaving(false);
    }, 800);
  }

  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      if (dirtyRef.current && rowsRef.current.length > 0) {
        saveTransactions(bankId, accountSlug, rowsRef.current);
      }
    };
  }, [bankId, accountSlug]);

  async function loadData() {
    const data = await getTransactions(bankId, accountSlug);
    if (data.transactions.length > 0) setRows(data.transactions);
    setDirty(false);
  }

  async function handleFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    await uploadTransactions(bankId, accountSlug, file);
    await loadData();
    flash('success', `CSV uploaded — ${file.name}`);
  }

  // Sort + recalc helper
  function sortAndRecalc(updatedRows) {
    const sorted = sortOrder === 'asc'
      ? [...updatedRows].sort((a, b) => parseDateSort(a.date) - parseDateSort(b.date))
      : sortByDateDesc(updatedRows);
    return fullRecalc(sorted);
  }

  function updateRow(idx, field, value) {
    const updated = rows.map((r, i) => i === idx ? { ...r, [field]: value } : r);

    if (field === 'date') {
      // Date changed — re-sort and recalculate everything
      const result = sortAndRecalc(updated);
      setRows(result);
      setDirty(true);
      scheduleAutoSave(result);
    } else if (field === 'credit' || field === 'debit') {
      const result = fullRecalc(updated);
      setRows(result);
      setDirty(true);
      scheduleAutoSave(result);
    } else {
      setRows(updated);
      setDirty(true);
      scheduleAutoSave(updated);
    }
  }

  function addEmptyRow() {
    const updated = [...rows, makeEmptyRow(columns)];
    setRows(updated);
    setDirty(true);
    scheduleAutoSave(updated);
  }

  function removeRow(idx) {
    let updated = rows.filter((_, i) => i !== idx);
    updated = fullRecalc(updated);
    setRows(updated);
    setDirty(true);
    scheduleAutoSave(updated);
  }

  // Sort button handler
  function handleSort() {
    const newOrder = sortOrder === 'desc' ? 'asc' : 'desc';
    setSortOrder(newOrder);
    const sorted = newOrder === 'asc'
      ? [...rows].sort((a, b) => parseDateSort(a.date) - parseDateSort(b.date))
      : sortByDateDesc(rows);
    const result = fullRecalc(sorted);
    setRows(result);
    setDirty(true);
    scheduleAutoSave(result);
    flash('success', `Sorted ${newOrder === 'desc' ? 'newest' : 'oldest'} first & recalculated`);
  }

  // ── Drag & drop (same-date reorder) ──
  function canDrag(fromIdx, toIdx) {
    if (fromIdx === toIdx) return false;
    const fromDate = parseDateSort(rows[fromIdx]?.date);
    const toDate = parseDateSort(rows[toIdx]?.date);
    return fromDate === toDate && fromDate !== 0;
  }

  function handleDragStart(e, idx) {
    setDragIdx(idx);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', idx);
  }

  function handleDragOver(e, idx) {
    e.preventDefault();
    if (dragIdx !== null && canDrag(dragIdx, idx)) {
      e.dataTransfer.dropEffect = 'move';
      setDragOverIdx(idx);
    } else {
      e.dataTransfer.dropEffect = 'none';
      setDragOverIdx(null);
    }
  }

  function handleDrop(e, toIdx) {
    e.preventDefault();
    const fromIdx = dragIdx;
    setDragIdx(null);
    setDragOverIdx(null);
    if (fromIdx === null || fromIdx === toIdx) return;
    if (!canDrag(fromIdx, toIdx)) return;

    const updated = [...rows];
    const [moved] = updated.splice(fromIdx, 1);
    updated.splice(toIdx, 0, moved);
    const result = fullRecalc(updated);
    setRows(result);
    setDirty(true);
    scheduleAutoSave(result);
  }

  function handleDragEnd() {
    setDragIdx(null);
    setDragOverIdx(null);
  }

  function updateNewTxn(idx, field, value) {
    setNewTxns(prev => prev.map((t, i) => i === idx ? { ...t, [field]: value } : t));
  }

  async function handleAddTransactions() {
    const valid = newTxns
      .filter(t => t.date && t.description && (t.credit || t.debit))
      .map(t => ({
        date: htmlDateToCsv(t.date),
        description: t.description,
        credit: t.credit ? parseFloat(t.credit) : null,
        debit: t.debit ? parseFloat(t.debit) : null,
      }));
    if (valid.length === 0) {
      flash('error', 'Fill in date, description, and either credit or debit');
      return;
    }
    setAdding(true);
    try {
      const result = await addTransactions(bankId, accountSlug, valid);
      flash('success', `Added ${result.added} transaction(s). Total: ${result.total}`);
      await loadData();
      setNewTxns([{}]);
      setShowAddForm(false);
    } catch (err) {
      flash('error', err.message);
    }
    setAdding(false);
  }

  async function handleRecalculate() {
    await recalculateBalances(bankId, accountSlug);
    await loadData();
    flash('success', 'All balances recalculated');
  }

  async function handleSave() {
    setSaving(true);
    await saveTransactions(bankId, accountSlug, rows);
    setDirty(false);
    setSaving(false);
    onDone();
  }

  function flash(type, text) {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 4000);
  }

  function downloadCsv() {
    const csvHeaders = bankFields?.csvHeaders || columns.map(c => c.label).join(',');
    const csvRows = rows.map(r => {
      const fields = columns.map(c => r[c.key] ?? '');
      return fields.map(f => {
        const s = String(f ?? '');
        return s.includes(',') || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s;
      }).join(',');
    });
    const blob = new Blob([csvHeaders + '\n' + csvRows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'transactions.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  async function copyCsvPrompt() {
    const csvHeaders = bankFields?.csvHeaders || 'Date,Description,Credit,Debit,Balance';
    const csvExample = bankFields?.csvExample || `Date,Description,Credit,Debit,Balance\n27/03/2026,TRANSFER - Mubaraq Basha,,57.00,18076.06`;
    const colDescs = columns.map(c => {
      let desc = `- ${c.label}: `;
      if (c.key === 'date' || c.key === 'value_date') desc += 'DD/MM/YYYY format';
      else if (c.key === 'credit') desc += 'amount if money was RECEIVED (empty if 0)';
      else if (c.key === 'debit') desc += 'amount if money was SPENT (empty if 0)';
      else if (c.key === 'balance') desc += 'running balance AFTER the transaction (always present)';
      else if (c.key === 'ref') desc += 'cheque/reference number';
      else if (c.key === 'description') desc += 'transaction narration/description';
      return desc;
    }).join('\n');
    const prompt = `I need you to generate a bank statement transactions CSV file. Return ONLY the raw CSV content, no explanation, no markdown code fences.\n\nFORMAT RULES:\n- Header row: ${csvHeaders}\n- Rows ordered NEWEST FIRST\n${colDescs}\n- Amounts: plain numbers with 2 decimals, no commas\n- Balance must be mathematically consistent\n- Date format: DD/MM/YYYY\n\nEXAMPLE:\n${csvExample}\n\nGENERATE:\n- Account: ${accountSlug || 'savings account'}\n- Bank: ${bankId || 'bank'}\n- Number of transactions: 50 (spanning the last 2 months)\n- Mix of debits and credits\n- Starting balance: around 50,000\n\nReturn ONLY the CSV. No other text.`;
    try { await navigator.clipboard.writeText(prompt); } catch {
      const ta = document.createElement('textarea'); ta.value = prompt; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta);
    }
    setCsvPromptCopied(true);
    setTimeout(() => setCsvPromptCopied(false), 3000);
    flash('success', 'CSV prompt copied!');
  }

  const filtered = search
    ? rows.filter(r => {
        const q = search.toLowerCase();
        return columns.some(c => String(r[c.key] || '').toLowerCase().includes(q));
      })
    : rows;

  return (
    <div className="space-y-4">
      {message && (
        <div className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm animate-fade-in
          ${message.type === 'success' ? 'bg-green-50 text-green-700 border border-green-200' : 'bg-red-50 text-red-700 border border-red-200'}`}>
          <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            {message.type === 'success'
              ? <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              : <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />}
          </svg>
          {message.text}
        </div>
      )}

      {/* Toolbar */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <button onClick={() => setShowAddForm(!showAddForm)}
              className={`text-xs font-medium px-3 py-2 rounded-lg flex items-center gap-1.5 transition
                ${showAddForm ? 'bg-gray-100 text-gray-700' : 'bg-blue-600 text-white hover:bg-blue-700 shadow-sm'}`}>
              {showAddForm
                ? <><svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>Cancel</>
                : <><svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>Add Transaction</>}
            </button>
            <button onClick={handleRecalculate}
              className="text-xs text-gray-600 px-3 py-2 rounded-lg hover:bg-gray-100 transition flex items-center gap-1.5">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
              </svg>
              Recalculate
            </button>
            <button onClick={handleSort}
              className="text-xs text-gray-600 px-3 py-2 rounded-lg hover:bg-gray-100 transition flex items-center gap-1.5"
              title={`Sort ${sortOrder === 'desc' ? 'oldest' : 'newest'} first`}>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 7.5L7.5 3m0 0L12 7.5M7.5 3v13.5m13.5-4.5L16.5 16.5m0 0L12 12m4.5 4.5V3" />
              </svg>
              Sort {sortOrder === 'desc' ? '↑' : '↓'}
            </button>
          </div>

          <div className="flex items-center gap-2">
            <div className="relative">
              <svg className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
              </svg>
              <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search..."
                className="pl-8 pr-3 py-1.5 text-xs border border-gray-200 rounded-lg w-44 focus:border-blue-500 focus:ring-1 focus:ring-blue-500 outline-none" />
            </div>
            <label className="text-xs text-gray-500 hover:text-blue-600 cursor-pointer px-2 py-1.5 rounded-lg hover:bg-gray-50 transition">
              Upload CSV
              <input type="file" accept=".csv" onChange={handleFileUpload} className="hidden" />
            </label>
            <button onClick={copyCsvPrompt}
              className={`text-xs px-2 py-1.5 rounded-lg transition flex items-center gap-1
                ${csvPromptCopied ? 'text-green-600 bg-green-50' : 'text-gray-500 hover:text-blue-600 hover:bg-gray-50'}`}>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" /></svg>
              {csvPromptCopied ? 'Copied!' : 'CSV Prompt'}
            </button>
            {rows.length > 0 && (
              <button onClick={downloadCsv}
                className="text-xs text-gray-500 hover:text-blue-600 px-2 py-1.5 rounded-lg hover:bg-gray-50 transition flex items-center gap-1">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                </svg>
                Download CSV
              </button>
            )}
            <span className="text-[11px] text-gray-400 tabular-nums">{rows.length} rows</span>
          </div>
        </div>

        {showAddForm && (
          <div className="px-4 py-4 bg-blue-50 border-t border-blue-100 animate-slide-up">
            <div className="space-y-2">
              {newTxns.map((nt, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <input type="date" value={nt.date || ''} onChange={e => updateNewTxn(i, 'date', e.target.value)}
                    className="border border-blue-200 rounded-lg px-2.5 py-1.5 text-xs w-36 bg-white focus:border-blue-500 outline-none" />
                  <input value={nt.description || ''} onChange={e => updateNewTxn(i, 'description', e.target.value)}
                    placeholder={columns.find(c => c.key === 'description')?.label || 'Description'}
                    className="flex-1 border border-blue-200 rounded-lg px-2.5 py-1.5 text-xs bg-white focus:border-blue-500 outline-none" />
                  <input value={nt.credit || ''} onChange={e => updateNewTxn(i, 'credit', e.target.value)}
                    placeholder={creditCol?.label || 'Credit'} type="number" step="0.01" min="0"
                    className="w-24 border border-blue-200 rounded-lg px-2.5 py-1.5 text-xs text-right bg-white focus:border-blue-500 outline-none" />
                  <input value={nt.debit || ''} onChange={e => updateNewTxn(i, 'debit', e.target.value)}
                    placeholder={debitCol?.label || 'Debit'} type="number" step="0.01" min="0"
                    className="w-24 border border-blue-200 rounded-lg px-2.5 py-1.5 text-xs text-right bg-white focus:border-blue-500 outline-none" />
                  {newTxns.length > 1 && (
                    <button onClick={() => setNewTxns(prev => prev.filter((_, j) => j !== i))}
                      className="text-blue-400 hover:text-red-500 p-1 transition">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  )}
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between mt-3">
              <button onClick={() => setNewTxns(prev => [...prev, {}])}
                className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1">
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                Add another row
              </button>
              <button onClick={handleAddTransactions} disabled={adding}
                className="text-xs font-medium bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition shadow-sm">
                {adding ? 'Adding...' : 'Add & Recalculate'}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Transaction Table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto max-h-[520px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10">
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="px-1 py-2.5 w-6"></th>
                {columns.map(col => (
                  <th key={col.key}
                    className={`px-3 py-2.5 text-xs font-medium text-gray-500 uppercase tracking-wider
                      ${col.type === 'amount' ? 'text-right' : 'text-left'}
                      ${col.width || ''}`}>
                    {col.label}
                  </th>
                ))}
                <th className="px-2 py-2.5 w-8"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={columns.length + 2} className="px-4 py-12 text-center">
                    <div className="text-gray-400 text-sm">
                      {search ? 'No transactions match your search.' : 'No transactions yet.'}
                    </div>
                    {!search && (
                      <button onClick={addEmptyRow} className="mt-3 text-xs text-blue-600 hover:text-blue-800">
                        + Add a transaction manually
                      </button>
                    )}
                  </td>
                </tr>
              ) : (
                filtered.map((row, i) => {
                  const realIdx = rows.indexOf(row);
                  const sameDate = dragIdx !== null && parseDateSort(rows[dragIdx]?.date) === parseDateSort(row.date) && parseDateSort(row.date) !== 0;
                  const isDragOver = dragOverIdx === realIdx;
                  return (
                    <tr key={realIdx}
                      className={`group transition-colors
                        ${isDragOver ? 'bg-blue-50 border-t-2 border-blue-400' : 'hover:bg-gray-50'}
                        ${dragIdx === realIdx ? 'opacity-40' : ''}`}
                      draggable={sameDate || dragIdx === null}
                      onDragStart={e => handleDragStart(e, realIdx)}
                      onDragOver={e => handleDragOver(e, realIdx)}
                      onDrop={e => handleDrop(e, realIdx)}
                      onDragEnd={handleDragEnd}>
                      {/* Drag handle */}
                      <td className="px-1 py-1 w-6">
                        <div className="cursor-grab active:cursor-grabbing text-gray-300 hover:text-gray-500 flex items-center justify-center"
                          title="Drag to reorder (same date only)">
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
                          </svg>
                        </div>
                      </td>
                      {columns.map(col => (
                        <td key={col.key} className="px-2 py-1">
                          {col.readonly ? (
                            <div className={`px-2 py-1.5 text-xs text-gray-500 font-mono tabular-nums
                              ${col.type === 'amount' ? 'text-right' : ''}`}>
                              {row[col.key]}
                            </div>
                          ) : (
                            <input
                              value={row[col.key] || ''}
                              onChange={e => updateRow(realIdx, col.key, e.target.value)}
                              className={`w-full px-2 py-1.5 text-xs border border-transparent rounded
                                group-hover:border-gray-200 focus:border-blue-500 focus:ring-1 focus:ring-blue-500
                                outline-none bg-transparent
                                ${col.type === 'amount' ? 'text-right tabular-nums font-mono' : ''}
                                ${col.color === 'green' ? 'text-green-700' : ''}
                                ${col.color === 'red' ? 'text-red-600' : ''}
                                ${col.flex ? 'truncate' : ''}`}
                              placeholder={col.label}
                            />
                          )}
                        </td>
                      ))}
                      <td className="px-1 py-1">
                        <button onClick={() => removeRow(realIdx)}
                          className="p-1 text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition">
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="px-4 py-2.5 bg-gray-50 border-t border-gray-100 flex items-center justify-between">
          <button onClick={addEmptyRow} className="text-xs text-gray-500 hover:text-blue-600 flex items-center gap-1 transition">
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            Add row
          </button>
          {autoSaving ? (
            <span className="text-[11px] text-blue-500 flex items-center gap-1">
              <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Saving...
            </span>
          ) : dirty ? (
            <span className="text-[11px] text-amber-600">Unsaved changes</span>
          ) : rows.length > 0 ? (
            <span className="text-[11px] text-green-600 flex items-center gap-1">
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
              Saved
            </span>
          ) : null}
        </div>
      </div>

      <div className="flex justify-end">
        <button onClick={handleSave} disabled={saving || rows.length === 0}
          className="px-6 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg
            hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50 transition shadow-sm hover:shadow flex items-center gap-2">
          {saving ? (
            <><svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg>Saving...</>
          ) : 'Save & Continue'}
        </button>
      </div>
    </div>
  );
}
