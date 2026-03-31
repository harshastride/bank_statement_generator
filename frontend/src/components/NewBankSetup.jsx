import { useState, useRef } from 'react';
import { analyzePdf, buildTemplate, listBanks } from '../api';

const SETUP_STEPS = [
  { id: 1, label: 'Upload PDF', desc: 'Upload source statement' },
  { id: 2, label: 'Get Profile', desc: 'Use Claude to extract layout' },
  { id: 3, label: 'Upload Profile', desc: 'Upload profile.json' },
  { id: 4, label: 'Register Bank', desc: 'Name and save the bank' },
];

export default function NewBankSetup() {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Step 1
  const [pdfFile, setPdfFile] = useState(null);
  const [analyzerResult, setAnalyzerResult] = useState(null);
  const pdfRef = useRef();

  // Step 2
  const [copied, setCopied] = useState(false);

  // Step 3
  const [profileJson, setProfileJson] = useState(null);
  const [profileValidation, setProfileValidation] = useState(null);
  const [profileMode, setProfileMode] = useState('file'); // 'file' | 'paste'
  const [pasteText, setPasteText] = useState('');
  const profileRef = useRef();

  // Step 4
  const [bankName, setBankName] = useState('');
  const [bankId, setBankId] = useState('');
  const [buildResult, setBuildResult] = useState(null);

  // ── Step 1: Upload PDF ──
  async function handleUploadPdf() {
    if (!pdfFile) return;
    setLoading(true);
    setError('');
    try {
      const result = await analyzePdf(pdfFile);
      setAnalyzerResult(result);
      setStep(2);
    } catch (err) {
      setError(err.message || 'Analysis failed');
    } finally {
      setLoading(false);
    }
  }

  // ── Step 2: Download PDF + Download JSON + Copy prompt ──
  function handleDownloadPdf() {
    if (!pdfFile) return;
    const url = URL.createObjectURL(pdfFile);
    const a = document.createElement('a');
    a.href = url;
    a.download = pdfFile.name || 'statement.pdf';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function handleDownloadAnalyzerJson() {
    if (!analyzerResult?.layout) return;
    const json = JSON.stringify(analyzerResult.layout, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'analyzer_output.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  function buildPrompt() {
    if (!analyzerResult) return '';
    let prompt = analyzerResult.prompt_template || '';
    // Remove the placeholder — the JSON is now a separate file attachment
    prompt = prompt.replace(
      '```json\n<<PASTE layout_for_claude.json CONTENTS HERE>>\n```',
      '(See the attached analyzer_output.json file for the exact coordinates)'
    );
    prompt = prompt.replace(
      '<<PASTE layout_for_claude.json CONTENTS HERE>>',
      '(See the attached analyzer_output.json file for the exact coordinates)'
    );
    return prompt;
  }

  async function handleCopyPrompt() {
    const prompt = buildPrompt();
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = prompt;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 3000);
    }
  }

  // ── Step 3: Validate and load profile ──
  function validateAndLoadProfile(text) {
    // Clean up: strip markdown code fences if Claude wrapped it
    let cleaned = text.trim();
    if (cleaned.startsWith('```')) {
      const lines = cleaned.split('\n');
      cleaned = lines.filter(l => !l.trim().startsWith('```')).join('\n');
    }

    const parsed = JSON.parse(cleaned);

    const columns = parsed.columns || [];
    const fonts = parsed.fonts || {};
    const headerFields = parsed.header_fields || [];

    if (columns.length < 2) throw new Error('Profile must have at least 2 columns');
    if (!fonts.transaction) throw new Error('Profile must have a "transaction" font');

    setProfileJson(parsed);
    setProfileValidation({
      columns: columns.map(c => c.name),
      fontRoles: Object.keys(fonts).length,
      headerFields: headerFields.length,
      pageSize: `${parsed.page_width || '?'} x ${parsed.page_height || '?'}`,
      hasRectPatterns: (parsed.header_row_rects_pattern || []).length > 0,
    });
    setStep(4);
  }

  async function handleProfileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    setError('');
    try {
      const text = await file.text();
      validateAndLoadProfile(text);
    } catch (err) {
      setError(`Invalid profile.json: ${err.message}`);
      setProfileJson(null);
      setProfileValidation(null);
    }
  }

  function handlePasteValidate() {
    setError('');
    try {
      validateAndLoadProfile(pasteText);
    } catch (err) {
      setError(`Invalid JSON: ${err.message}`);
      setProfileJson(null);
      setProfileValidation(null);
    }
  }

  // ── Step 4: Register bank ──
  async function handleBuildTemplate() {
    if (!profileJson || !bankName.trim()) return;
    setLoading(true);
    setError('');
    try {
      const id = bankId.trim() || bankName.trim().toLowerCase().replace(/\s+/g, '_');
      const result = await buildTemplate(profileJson, bankName.trim(), id);
      setBuildResult(result);
    } catch (err) {
      setError(err.message || 'Build failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-3xl">
      {/* Step indicators */}
      <div className="flex items-center gap-2 mb-8">
        {SETUP_STEPS.map((s, i) => (
          <div key={s.id} className="flex items-center gap-2">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition
              ${step > s.id ? 'bg-green-100 text-green-700' :
                step === s.id ? 'bg-blue-600 text-white' :
                'bg-gray-100 text-gray-400'}`}
            >
              {step > s.id ? (
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
              ) : s.id}
            </div>
            <span className={`text-xs font-medium ${step >= s.id ? 'text-gray-700' : 'text-gray-400'}`}>
              {s.label}
            </span>
            {i < SETUP_STEPS.length - 1 && <div className="w-8 h-px bg-gray-200" />}
          </div>
        ))}
      </div>

      {error && (
        <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl text-sm text-red-700">
          {error}
        </div>
      )}

      {/* ── Step 1: Upload PDF ── */}
      {step === 1 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 animate-fade-in">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Upload Source Statement PDF</h2>
          <p className="text-sm text-gray-500 mb-6">
            Upload an original bank statement PDF. This will be analyzed to extract the exact layout,
            fonts, images, and coordinates needed to generate matching statements.
          </p>

          <div
            onClick={() => pdfRef.current?.click()}
            className={`flex flex-col items-center justify-center gap-3 p-8 border-2 border-dashed rounded-xl cursor-pointer transition
              ${pdfFile ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-gray-400 hover:bg-gray-50'}`}
          >
            <svg className={`w-10 h-10 ${pdfFile ? 'text-blue-500' : 'text-gray-300'}`} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m6.75 12H9.75m0 0l2.25-2.25M9.75 14.25l2.25 2.25M6 20.25h12A2.25 2.25 0 0020.25 18V6.75A2.25 2.25 0 0018 4.5H6A2.25 2.25 0 003.75 6.75v11.25c0 1.243 1.007 2.25 2.25 2.25z" />
            </svg>
            <div className="text-center">
              <div className="text-sm font-medium text-gray-700">
                {pdfFile ? pdfFile.name : 'Click to select PDF'}
              </div>
              <div className="text-xs text-gray-400 mt-1">
                {pdfFile ? `${(pdfFile.size / 1024).toFixed(1)} KB` : 'Any bank statement PDF'}
              </div>
            </div>
          </div>
          <input ref={pdfRef} type="file" accept=".pdf" className="hidden"
            onChange={e => setPdfFile(e.target.files[0] || null)} />

          <button onClick={handleUploadPdf} disabled={!pdfFile || loading}
            className="mt-6 inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white font-medium rounded-lg
              hover:bg-blue-700 transition shadow-sm text-sm disabled:opacity-50 disabled:cursor-not-allowed">
            {loading ? (
              <><svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg> Analyzing...</>
            ) : 'Analyze PDF'}
          </button>
        </div>
      )}

      {/* ── Step 2: Send to Claude ── */}
      {step === 2 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 animate-fade-in">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Send to Claude</h2>
          <p className="text-sm text-gray-500 mb-4">
            The PDF has been analyzed ({analyzerResult?.pages_analyzed} pages).
            Now download the files below and send them to Claude to extract the layout profile.
          </p>

          {/* Action cards */}
          <div className="space-y-3 mb-6">
            {/* Download PDF */}
            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-200">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-red-100 flex items-center justify-center">
                  <svg className="w-5 h-5 text-red-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                  </svg>
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-900">Statement PDF</div>
                  <div className="text-xs text-gray-500">Attach this file to Claude chat</div>
                </div>
              </div>
              <button onClick={handleDownloadPdf}
                className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                </svg>
                Download PDF
              </button>
            </div>

            {/* Download Analyzer JSON */}
            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-200">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-amber-100 flex items-center justify-center">
                  <svg className="w-5 h-5 text-amber-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M17.25 6.75L22.5 12l-5.25 5.25m-10.5 0L1.5 12l5.25-5.25m7.5-3l-4.5 16.5" />
                  </svg>
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-900">Analyzer Output (JSON)</div>
                  <div className="text-xs text-gray-500">Exact coordinates — attach this to Claude chat too</div>
                </div>
              </div>
              <button onClick={handleDownloadAnalyzerJson}
                className="inline-flex items-center gap-2 px-4 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                </svg>
                Download JSON
              </button>
            </div>

            {/* Copy Prompt */}
            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border border-gray-200">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                  <svg className="w-5 h-5 text-blue-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                  </svg>
                </div>
                <div>
                  <div className="text-sm font-medium text-gray-900">Claude Prompt</div>
                  <div className="text-xs text-gray-500">Includes analyzer data + extraction instructions</div>
                </div>
              </div>
              <button onClick={handleCopyPrompt}
                className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition
                  ${copied ? 'bg-green-100 text-green-700 border border-green-300' : 'bg-blue-600 text-white hover:bg-blue-700'}`}>
                {copied ? (
                  <><svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" /></svg> Copied!</>
                ) : (
                  <><svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" /></svg> Copy Prompt</>
                )}
              </button>
            </div>
          </div>

          {/* Instructions */}
          <div className="bg-blue-50 rounded-lg p-4 mb-6">
            <div className="text-sm font-medium text-blue-900 mb-3">How to use these in Claude:</div>
            <ol className="space-y-2 text-sm text-blue-800">
              <li className="flex items-start gap-2">
                <span className="w-5 h-5 rounded-full bg-blue-200 text-blue-800 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">1</span>
                Open <a href="https://claude.ai" target="_blank" rel="noreferrer" className="font-medium underline">claude.ai</a> and start a new chat
              </li>
              <li className="flex items-start gap-2">
                <span className="w-5 h-5 rounded-full bg-blue-200 text-blue-800 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">2</span>
                Attach <strong>both files</strong>: the Statement PDF + the Analyzer JSON
              </li>
              <li className="flex items-start gap-2">
                <span className="w-5 h-5 rounded-full bg-blue-200 text-blue-800 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">3</span>
                Paste the copied prompt into the message box and send
              </li>
              <li className="flex items-start gap-2">
                <span className="w-5 h-5 rounded-full bg-blue-200 text-blue-800 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">4</span>
                Claude returns a JSON — save it as <code className="bg-blue-100 px-1.5 py-0.5 rounded text-xs font-mono">profile.json</code>
              </li>
            </ol>
          </div>

          <button onClick={() => setStep(3)}
            className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white font-medium rounded-lg
              hover:bg-blue-700 transition shadow-sm text-sm">
            I have the profile.json
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
            </svg>
          </button>
        </div>
      )}

      {/* ── Step 3: Upload Profile ── */}
      {step === 3 && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 animate-fade-in">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Upload Profile</h2>
          <p className="text-sm text-gray-500 mb-4">
            Provide the profile JSON from Claude's response — upload a file or paste directly.
          </p>

          {/* Tab toggle */}
          <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5 mb-5 max-w-xs">
            <button onClick={() => setProfileMode('file')}
              className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition
                ${profileMode === 'file' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
              Upload File
            </button>
            <button onClick={() => setProfileMode('paste')}
              className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition
                ${profileMode === 'paste' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
              Paste JSON
            </button>
          </div>

          {profileMode === 'file' ? (
            <>
              <div
                onClick={() => profileRef.current?.click()}
                className={`flex items-center gap-4 p-5 border-2 border-dashed rounded-xl cursor-pointer transition
                  ${profileJson ? 'border-green-400 bg-green-50' : 'border-gray-300 hover:border-gray-400'}`}
              >
                <svg className={`w-8 h-8 ${profileJson ? 'text-green-600' : 'text-gray-300'}`} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m.75 12l3 3m0 0l3-3m-3 3v-6m-1.5-9H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
                <div>
                  <div className="text-sm font-medium text-gray-700">
                    {profileJson ? 'profile.json loaded' : 'Click to upload profile.json'}
                  </div>
                  {profileValidation && (
                    <div className="text-xs text-green-600 mt-1">
                      {profileValidation.columns.join(', ')} | {profileValidation.fontRoles} fonts
                    </div>
                  )}
                </div>
              </div>
              <input ref={profileRef} type="file" accept=".json" className="hidden"
                onChange={handleProfileUpload} />
            </>
          ) : (
            <>
              <textarea
                value={pasteText}
                onChange={e => setPasteText(e.target.value)}
                placeholder={"Paste Claude's JSON response here...\n\n{\n  \"page_width\": 594.96,\n  ...\n}"}
                className="w-full h-64 px-4 py-3 border border-gray-300 rounded-xl text-xs font-mono text-gray-800
                  focus:ring-2 focus:ring-blue-200 focus:border-blue-500 outline-none resize-y"
              />
              <button onClick={handlePasteValidate} disabled={!pasteText.trim()}
                className="mt-3 inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium
                  hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed">
                Validate JSON
              </button>
            </>
          )}

          {profileValidation && (
            <div className="mt-4 p-4 bg-green-50 border border-green-200 rounded-lg">
              <div className="text-sm font-medium text-green-800 mb-2">Profile validated</div>
              <div className="grid grid-cols-2 gap-2 text-xs text-green-700">
                <div>Columns: {profileValidation.columns.join(', ')}</div>
                <div>Page: {profileValidation.pageSize}</div>
                <div>Font roles: {profileValidation.fontRoles}</div>
                <div>Header fields: {profileValidation.headerFields}</div>
                <div>Rect patterns: {profileValidation.hasRectPatterns ? 'Yes' : 'No'}</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Step 4: Register Bank ── */}
      {step === 4 && !buildResult && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 animate-fade-in">
          <h2 className="text-lg font-semibold text-gray-900 mb-2">Register Bank</h2>
          <p className="text-sm text-gray-500 mb-6">
            Name this bank template. It will be available in the wizard for generating statements.
          </p>

          <div className="space-y-4 max-w-md">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Bank Name</label>
              <input type="text" value={bankName} onChange={e => setBankName(e.target.value)}
                placeholder="e.g., HDFC Bank"
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-200 focus:border-blue-500 outline-none" />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Bank ID (optional)</label>
              <input type="text" value={bankId} onChange={e => setBankId(e.target.value)}
                placeholder={bankName ? bankName.toLowerCase().replace(/\s+/g, '_') : 'auto-generated'}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-200 focus:border-blue-500 outline-none" />
              <div className="text-xs text-gray-400 mt-1">Used internally. Auto-generated from name if empty.</div>
            </div>
          </div>

          <button onClick={handleBuildTemplate} disabled={!bankName.trim() || loading}
            className="mt-6 inline-flex items-center gap-2 px-6 py-3 bg-green-600 text-white font-medium rounded-lg
              hover:bg-green-700 transition shadow-sm text-sm disabled:opacity-50 disabled:cursor-not-allowed">
            {loading ? (
              <><svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" /></svg> Building template...</>
            ) : (
              <><svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg> Build Template & Register Bank</>
            )}
          </button>
        </div>
      )}

      {/* ── Success ── */}
      {buildResult && (
        <div className="bg-white rounded-xl border border-green-200 shadow-sm p-6 animate-fade-in">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-full bg-green-100 flex items-center justify-center">
              <svg className="w-6 h-6 text-green-600" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
            </div>
            <div>
              <h2 className="text-lg font-semibold text-green-900">Bank Registered!</h2>
              <div className="text-sm text-green-700">{buildResult.bank_name} is ready to use</div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3 p-4 bg-green-50 rounded-lg text-sm">
            <div><span className="text-green-600 font-medium">Bank ID:</span> {buildResult.bank_id}</div>
            <div><span className="text-green-600 font-medium">Profile:</span> v{buildResult.profile_version}</div>
            <div><span className="text-green-600 font-medium">Columns:</span> {buildResult.columns?.join(', ')}</div>
            <div><span className="text-green-600 font-medium">Header fields:</span> {buildResult.header_fields}</div>
            <div><span className="text-green-600 font-medium">Footer:</span> {buildResult.has_footer ? `${buildResult.footer_spans} spans` : 'None'}</div>
          </div>

          <div className="mt-6 flex gap-3">
            <button onClick={() => { setStep(1); setPdfFile(null); setAnalyzerResult(null); setProfileJson(null); setProfileValidation(null); setBuildResult(null); setBankName(''); setBankId(''); }}
              className="inline-flex items-center gap-2 px-5 py-2.5 border border-gray-300 text-gray-700 font-medium rounded-lg
                hover:bg-gray-50 transition text-sm">
              Add Another Bank
            </button>
            <div className="text-sm text-gray-500 flex items-center">
              Go to Step-by-Step mode to create statements with this bank
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
