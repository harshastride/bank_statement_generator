import { useState, useEffect, useRef } from 'react';
import { getAccountData, saveAccountData, getBankFields } from '../api';

const FALLBACK_SECTIONS = [
  {
    title: 'Account Holder',
    fields: [
      { key: 'customer_name', label: 'Full Name', required: true, span: 2 },
      { key: 'address_line_1', label: 'Address Line 1' },
      { key: 'address_line_2', label: 'Address Line 2' },
      { key: 'city_state', label: 'City / State' },
      { key: 'pin', label: 'PIN Code' },
    ],
  },
  {
    title: 'Account Information',
    fields: [
      { key: 'account_number', label: 'Account Number', required: true },
      { key: 'account_type', label: 'Account Type', required: true },
      { key: 'branch', label: 'Branch Name' },
      { key: 'ifsc', label: 'IFSC Code' },
    ],
  },
  {
    title: 'Balance & Currency',
    fields: [
      { key: 'current_balance', label: 'Current Balance', required: true, mono: true },
      { key: 'currency', label: 'Currency' },
    ],
  },
];

export default function AccountForm({ bankId, accountSlug, onDone }) {
  const [form, setForm] = useState({});
  const [saving, setSaving] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [sections, setSections] = useState([]);
  const [viewMode, setViewMode] = useState('form'); // 'form' | 'json'
  const [jsonText, setJsonText] = useState('');
  const [jsonError, setJsonError] = useState('');
  const fileInputRef = useRef(null);

  useEffect(() => {
    Promise.all([
      getAccountData(bankId, accountSlug),
      getBankFields(bankId),
    ]).then(([data, fieldsRes]) => {
      const s = fieldsRes.sections && fieldsRes.sections.length > 0
        ? fieldsRes.sections
        : FALLBACK_SECTIONS;
      setSections(s);

      // Build a full form object with ALL fields from config, filled with saved data
      const full = {};
      s.forEach(section => {
        section.fields.forEach(f => {
          full[f.key] = data[f.key] || '';
        });
      });
      // Also keep any extra keys from saved data that aren't in the form config
      Object.keys(data).forEach(k => {
        if (full[k] === undefined) full[k] = data[k];
      });

      setForm(full);
      setJsonText(JSON.stringify(full, null, 2));
      setLoaded(true);
    });
  }, [bankId, accountSlug]);

  function update(key, val) {
    setForm(prev => {
      const next = { ...prev, [key]: val };
      setJsonText(JSON.stringify(next, null, 2));
      return next;
    });
  }

  function handleJsonChange(text) {
    setJsonText(text);
    setJsonError('');
    try {
      const parsed = JSON.parse(text);
      if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
        setForm(parsed);
        setJsonError('');
      } else {
        setJsonError('Must be a JSON object');
      }
    } catch {
      setJsonError('Invalid JSON');
    }
  }

  function handleJsonUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = ev.target.result;
      try {
        const parsed = JSON.parse(text);
        if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
          setForm(parsed);
          setJsonText(JSON.stringify(parsed, null, 2));
          setJsonError('');
        } else {
          setJsonError('File must contain a JSON object');
        }
      } catch {
        setJsonError('File contains invalid JSON');
      }
    };
    reader.readAsText(file);
    e.target.value = '';
  }

  function downloadJson() {
    const blob = new Blob([JSON.stringify(form, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'account_data.json';
    a.click();
    URL.revokeObjectURL(url);
  }

  function switchToForm() {
    setViewMode('form');
    // Sync any valid JSON edits back to form
    try {
      const parsed = JSON.parse(jsonText);
      if (typeof parsed === 'object' && parsed !== null) setForm(parsed);
    } catch { /* keep current form state */ }
  }

  function switchToJson() {
    setJsonText(JSON.stringify(form, null, 2));
    setJsonError('');
    setViewMode('json');
  }

  async function handleSave() {
    if (viewMode === 'json') {
      try {
        const parsed = JSON.parse(jsonText);
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          setJsonError('Must be a JSON object');
          return;
        }
        setForm(parsed);
      } catch {
        setJsonError('Fix JSON errors before saving');
        return;
      }
    }
    setSaving(true);
    await saveAccountData(bankId, accountSlug, form);
    setSaving(false);
    onDone();
  }

  if (!loaded) {
    return (
      <div className="space-y-6 max-w-2xl">
        {[1, 2, 3].map(i => (
          <div key={i} className="bg-white rounded-xl border border-gray-200 p-6">
            <div className="skeleton h-4 w-32 mb-4" />
            <div className="grid grid-cols-2 gap-4">
              <div className="skeleton h-9 rounded-lg" />
              <div className="skeleton h-9 rounded-lg" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      {/* Mode Toggle + Actions */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5">
          <button onClick={switchToForm}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition
              ${viewMode === 'form' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
            Form
          </button>
          <button onClick={switchToJson}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition
              ${viewMode === 'json' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
            JSON
          </button>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-500 hover:text-blue-600 cursor-pointer px-2 py-1.5 rounded-lg hover:bg-gray-50 transition flex items-center gap-1">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
            Upload JSON
            <input ref={fileInputRef} type="file" accept=".json" onChange={handleJsonUpload} className="hidden" />
          </label>
          <button onClick={downloadJson}
            className="text-xs text-gray-500 hover:text-blue-600 px-2 py-1.5 rounded-lg hover:bg-gray-50 transition flex items-center gap-1">
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
            Download JSON
          </button>
        </div>
      </div>

      {viewMode === 'form' ? (
        /* ── Form View ── */
        <div className="space-y-5">
          {sections.map(section => (
            <div key={section.title} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="px-5 py-3 bg-gray-50 border-b border-gray-100">
                <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{section.title}</h3>
              </div>
              <div className="px-5 py-4">
                <div className="grid grid-cols-2 gap-x-4 gap-y-3">
                  {section.fields.map(f => (
                    <div key={f.key} className={f.span === 2 ? 'col-span-2' : ''}>
                      <label className="block text-xs font-medium text-gray-600 mb-1">
                        {f.label}
                        {f.required && <span className="text-red-400 ml-0.5">*</span>}
                      </label>
                      <input
                        value={form[f.key] || ''}
                        onChange={e => update(f.key, e.target.value)}
                        className={`w-full px-3 py-2 text-sm border border-gray-200 rounded-lg
                          bg-white hover:border-gray-300 focus:border-blue-500 focus:ring-1 focus:ring-blue-500
                          outline-none transition placeholder:text-gray-300
                          ${f.mono ? 'font-mono tabular-nums' : ''}`}
                        placeholder={f.placeholder || f.label}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : (
        /* ── JSON View ── */
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-5 py-3 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">account_data.json</h3>
            {jsonError && (
              <span className="text-xs text-red-500 flex items-center gap-1">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                </svg>
                {jsonError}
              </span>
            )}
          </div>
          <textarea
            value={jsonText}
            onChange={e => handleJsonChange(e.target.value)}
            spellCheck={false}
            className={`w-full px-5 py-4 text-sm font-mono leading-relaxed border-0 outline-none resize-none bg-white
              ${jsonError ? 'text-red-700' : 'text-gray-800'}`}
            style={{ minHeight: '420px' }}
          />
        </div>
      )}

      {/* Save Button */}
      <div className="mt-6 flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving || (viewMode === 'json' && !!jsonError)}
          className="px-6 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg
            hover:bg-blue-700 active:bg-blue-800 disabled:opacity-50 transition
            shadow-sm hover:shadow flex items-center gap-2"
        >
          {saving ? (
            <>
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Saving...
            </>
          ) : 'Save & Continue'}
        </button>
      </div>
    </div>
  );
}
