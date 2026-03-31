import { useState, useEffect, useCallback } from 'react';
import { listJobs, generatePdfRange, downloadUrl } from '../api';

export default function GenerateRange() {
  const [jobs, setJobs] = useState([]);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [selectedJob, setSelectedJob] = useState(null);
  const [copiedId, setCopiedId] = useState(null);

  // Date range
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [useFullRange, setUseFullRange] = useState(true);

  // Generate
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);

  useEffect(() => {
    loadJobs();
  }, []);

  async function loadJobs() {
    setLoadingJobs(true);
    try {
      const data = await listJobs();
      setJobs(data.jobs || []);
    } catch (err) {
      setError('Failed to load jobs');
    } finally {
      setLoadingJobs(false);
    }
  }

  function formatDateForApi(htmlDate) {
    if (!htmlDate) return '';
    const [y, m, d] = htmlDate.split('-');
    return `${d}/${m}/${y}`;
  }

  async function handleGenerate() {
    if (!selectedJob) {
      setError('Please select a job first');
      return;
    }
    if (!useFullRange && (!startDate || !endDate)) {
      setError('Please select both start and end dates');
      return;
    }

    setLoading(true);
    setError('');
    try {
      const start = useFullRange ? '01/01/2000' : formatDateForApi(startDate);
      const end = useFullRange ? '31/12/2099' : formatDateForApi(endDate);
      const res = await generatePdfRange(selectedJob.job_id, start, end);
      setResult(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setResult(null);
    setError('');
  }

  // ── Result view ──
  if (result && selectedJob) {
    return (
      <div className="space-y-6 animate-slide-up">
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden max-w-xl">
          <div className="px-6 py-8 text-center">
            <div className="mx-auto w-14 h-14 rounded-full bg-green-100 flex items-center justify-center mb-4">
              <svg className="w-7 h-7 text-green-600" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-1">PDF Generated</h3>
            <p className="text-sm text-gray-500">
              {(result.size / 1024).toFixed(0)} KB &middot; {result.filtered_transactions} of {result.total_transactions} transactions
            </p>
            {!useFullRange && result.date_range && (
              <p className="text-xs text-gray-400 mt-1">
                {result.date_range.start} &rarr; {result.date_range.end}
              </p>
            )}
            <div className="mt-6 flex items-center justify-center gap-3">
              <a href={downloadUrl(selectedJob.job_id)} download="statement.pdf"
                className="inline-flex items-center gap-2 px-6 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg
                  hover:bg-blue-700 transition shadow-sm hover:shadow">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                </svg>
                Download PDF
              </a>
              <button onClick={handleReset}
                className="px-4 py-2.5 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition">
                Generate Another
              </button>
            </div>
          </div>
        </div>

        {/* Preview */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b border-gray-100 flex items-center justify-between">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Preview</h3>
            <a href={downloadUrl(selectedJob.job_id)} target="_blank" rel="noreferrer"
              className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1">
              Open in new tab
              <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
              </svg>
            </a>
          </div>
          <iframe
            src={downloadUrl(selectedJob.job_id)}
            className="w-full border-0"
            style={{ height: '70vh', minHeight: '500px' }}
            title="PDF Preview"
          />
        </div>
      </div>
    );
  }

  // ── Main view ──
  return (
    <div className="max-w-2xl space-y-6">
      {/* Job Selection */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100">
          <h3 className="text-sm font-semibold text-gray-900">Select Statement</h3>
          <p className="text-xs text-gray-500 mt-0.5">Choose from previously uploaded statement data</p>
        </div>

        <div className="px-6 py-4">
          {loadingJobs ? (
            <div className="flex items-center gap-3 text-gray-400 py-4">
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="text-sm">Loading jobs...</span>
            </div>
          ) : jobs.length === 0 ? (
            <div className="text-center py-8">
              <div className="mx-auto w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mb-3">
                <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 13.5h3.86a2.25 2.25 0 012.012 1.244l.256.512a2.25 2.25 0 002.013 1.244h3.218a2.25 2.25 0 002.013-1.244l.256-.512a2.25 2.25 0 012.013-1.244h3.859" />
                </svg>
              </div>
              <p className="text-sm text-gray-500">No completed jobs found.</p>
              <p className="text-xs text-gray-400 mt-1">Use the Step-by-Step mode to upload statement data first.</p>
            </div>
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto">
              {jobs.map(job => (
                <button
                  key={job.job_id}
                  onClick={() => { setSelectedJob(job); setResult(null); setError(''); }}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg border text-left transition
                    ${selectedJob?.job_id === job.job_id
                      ? 'border-blue-300 bg-blue-50 ring-1 ring-blue-200'
                      : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                    }`}
                >
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0
                    ${selectedJob?.job_id === job.job_id ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-500'}`}>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.75} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                    </svg>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900 truncate">{job.label}</div>
                    <div className="text-xs text-gray-500 flex items-center gap-1">
                      {job.txn_count} transactions &middot; ID: {job.job_id}
                      <span
                        role="button"
                        title="Copy Job ID"
                        onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(job.job_id); setCopiedId(job.job_id); setTimeout(() => setCopiedId(null), 1500); }}
                        className="inline-flex items-center ml-1 text-gray-400 hover:text-blue-600 cursor-pointer"
                      >
                        {copiedId === job.job_id ? (
                          <svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                          </svg>
                        ) : (
                          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9.75a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
                          </svg>
                        )}
                      </span>
                    </div>
                  </div>
                  {selectedJob?.job_id === job.job_id && (
                    <svg className="w-5 h-5 text-blue-600 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                    </svg>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Date Range - only show when job selected */}
      {selectedJob && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden animate-fade-in">
          <div className="px-6 py-4 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-900">Date Range</h3>
            <p className="text-xs text-gray-500 mt-0.5">Generate statement for all transactions or a specific period</p>
          </div>

          <div className="px-6 py-5 space-y-4">
            {/* Toggle */}
            <div className="flex gap-3">
              <button
                onClick={() => setUseFullRange(true)}
                className={`flex-1 px-4 py-3 rounded-lg border text-sm font-medium transition
                  ${useFullRange
                    ? 'border-blue-200 bg-blue-50 text-blue-700'
                    : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
                  }`}
              >
                <div className="flex items-center justify-center gap-2">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 12h16.5m-16.5 3.75h16.5M3.75 19.5h16.5M5.625 4.5h12.75a1.875 1.875 0 010 3.75H5.625a1.875 1.875 0 010-3.75z" />
                  </svg>
                  All Transactions
                </div>
              </button>
              <button
                onClick={() => setUseFullRange(false)}
                className={`flex-1 px-4 py-3 rounded-lg border text-sm font-medium transition
                  ${!useFullRange
                    ? 'border-blue-200 bg-blue-50 text-blue-700'
                    : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
                  }`}
              >
                <div className="flex items-center justify-center gap-2">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 3v2.25M17.25 3v2.25M3 18.75V7.5a2.25 2.25 0 012.25-2.25h13.5A2.25 2.25 0 0121 7.5v11.25m-18 0A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75m-18 0v-7.5A2.25 2.25 0 015.25 9h13.5A2.25 2.25 0 0121 11.25v7.5" />
                  </svg>
                  Custom Range
                </div>
              </button>
            </div>

            {/* Date pickers */}
            {!useFullRange && (
              <div className="flex gap-4 animate-fade-in">
                <div className="flex-1">
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">Start Date</label>
                  <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none" />
                </div>
                <div className="flex-1">
                  <label className="block text-xs font-medium text-gray-600 mb-1.5">End Date</label>
                  <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none" />
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Generate Button */}
      {selectedJob && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden animate-fade-in">
          <div className="px-6 py-8 text-center">
            {loading ? (
              <div className="animate-fade-in">
                <div className="mx-auto w-14 h-14 rounded-full bg-blue-100 flex items-center justify-center mb-4">
                  <svg className="w-6 h-6 text-blue-600 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-1">Generating PDF...</h3>
                <p className="text-sm text-gray-500">Filtering transactions and building pages</p>
                <div className="mt-6 mx-auto w-56 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                  <div className="h-full bg-blue-500 rounded-full" style={{
                    animation: 'shimmer 2s infinite',
                    background: 'linear-gradient(90deg, #3b82f6 25%, #60a5fa 50%, #3b82f6 75%)',
                    backgroundSize: '200% 100%',
                  }} />
                </div>
              </div>
            ) : (
              <>
                <div className="mx-auto w-14 h-14 rounded-full bg-gray-100 flex items-center justify-center mb-4">
                  <svg className="w-7 h-7 text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
                  </svg>
                </div>
                <h3 className="text-lg font-semibold text-gray-900 mb-1">Ready to generate</h3>
                <p className="text-sm text-gray-500 mb-6">
                  {useFullRange
                    ? `Generate statement with all ${selectedJob.txn_count} transactions`
                    : startDate && endDate
                      ? `Generate statement from ${startDate} to ${endDate}`
                      : 'Select a date range to generate'
                  }
                </p>
                <button onClick={handleGenerate}
                  className="inline-flex items-center gap-2 px-8 py-3 bg-blue-600 text-white font-medium rounded-lg
                    hover:bg-blue-700 active:bg-blue-800 transition shadow-sm hover:shadow text-base">
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
                  </svg>
                  Generate PDF
                </button>
              </>
            )}
          </div>

          {error && (
            <div className="px-6 py-3 bg-red-50 border-t border-red-100 flex items-center gap-2 animate-fade-in">
              <svg className="w-4 h-4 text-red-500 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
              </svg>
              <span className="text-xs text-red-700">{error}</span>
              <button onClick={() => setError('')} className="ml-auto text-red-400 hover:text-red-600 text-xs">Dismiss</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
