import { useState, useEffect } from 'react';
import { generatePdf, generatePdfRange, getTransactions, saveTransactions, statementDownloadUrl, statementHtmlUrl, getBankFields } from '../api';
import StatementHistory from './StatementHistory';

export default function GenerateDownload({ bankId, accountSlug, transactions }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [txnCount, setTxnCount] = useState(transactions?.length || 0);
  const [genMode, setGenMode] = useState('all'); // 'all' | 'range'
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [filename, setFilename] = useState('');
  const [printToPdf, setPrintToPdf] = useState(false);

  useEffect(() => {
    if (!transactions || transactions.length === 0) {
      getTransactions(bankId, accountSlug).then(data => {
        setTxnCount(data.transactions?.length || 0);
      });
    } else {
      setTxnCount(transactions.length);
    }
    getBankFields(bankId).then(data => {
      if (data.printToPdf) setPrintToPdf(true);
    });
  }, [bankId, accountSlug, transactions]);

  async function handleGenerate() {
    setLoading(true);
    setError('');
    try {
      if (transactions && transactions.length > 0) {
        await saveTransactions(bankId, accountSlug, transactions);
      }

      const opts = {};
      if (filename.trim()) opts.filename = filename.trim();

      let res;
      if (genMode === 'range' && startDate && endDate) {
        const fmt = d => { const [y,m,dd] = d.split('-'); return `${dd}/${m}/${y}`; };
        res = await generatePdfRange(bankId, accountSlug, fmt(startDate), fmt(endDate), opts);
      } else {
        res = await generatePdf(bankId, accountSlug, opts);
      }
      setResult(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const downloadLink = result?.filename
    ? statementDownloadUrl(bankId, accountSlug, result.filename)
    : null;

  if (result) {
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
              {result.filename} &middot; {(result.size / 1024).toFixed(0)} KB
              {result.filtered_transactions && ` \u00b7 ${result.filtered_transactions} transactions`}
            </p>
            <div className="mt-6 flex items-center justify-center gap-3">
              {downloadLink && (
                <a href={downloadLink} download={result.filename}
                  className="inline-flex items-center gap-2 px-6 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg
                    hover:bg-blue-700 transition shadow-sm hover:shadow">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
                  </svg>
                  Download PDF
                </a>
              )}
              <button onClick={() => setResult(null)}
                className="px-4 py-2.5 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition">
                Generate Another
              </button>
            </div>
          </div>
        </div>

        {downloadLink && (
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-4 py-3 bg-gray-50 border-b border-gray-100">
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Preview</h3>
            </div>
            <iframe src={downloadLink} className="w-full border-0" style={{ height: '70vh', minHeight: '500px' }} title="PDF Preview" />
          </div>
        )}

        <StatementHistory bankId={bankId} accountSlug={accountSlug} />
      </div>
    );
  }

  return (
    <div className="max-w-xl">
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-6 py-8">
          {loading ? (
            <div className="text-center animate-fade-in">
              <div className="mx-auto w-14 h-14 rounded-full bg-blue-100 flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-blue-600 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-1">Generating PDF...</h3>
              <p className="text-sm text-gray-500">Building pages from template and transaction data</p>
            </div>
          ) : (
            <>
              {/* Mode toggle */}
              <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5 mb-6 max-w-xs">
                <button onClick={() => setGenMode('all')}
                  className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition
                    ${genMode === 'all' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'}`}>
                  All Transactions
                </button>
                <button onClick={() => setGenMode('range')}
                  className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition
                    ${genMode === 'range' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'}`}>
                  Date Range
                </button>
              </div>

              {genMode === 'range' && (
                <div className="flex gap-3 mb-6">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Start Date</label>
                    <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
                      className="px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-200" />
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">End Date</label>
                    <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)}
                      className="px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-200" />
                  </div>
                </div>
              )}

              {/* Filename */}
              <div className="mb-6">
                <label className="block text-xs font-medium text-gray-600 mb-1">File Name (optional)</label>
                <div className="flex items-center gap-1">
                  <input type="text" value={filename} onChange={e => setFilename(e.target.value)}
                    placeholder="e.g. hdfc_march_2026"
                    className="flex-1 px-3 py-2 border border-gray-200 rounded-lg text-sm outline-none
                      focus:ring-2 focus:ring-blue-200 font-mono placeholder:text-gray-300" />
                  <span className="text-sm text-gray-400">.pdf</span>
                </div>
                <p className="text-xs text-gray-400 mt-1">Leave blank for auto-generated name</p>
              </div>

              <div className="text-center">
                <p className="text-sm text-gray-500 mb-6">
                  {txnCount} transactions ready
                  {genMode === 'range' && startDate && endDate && ' (will filter by date range)'}
                </p>
                <div className="flex items-center justify-center gap-3 flex-wrap">
                  <button onClick={handleGenerate}
                    disabled={genMode === 'range' && (!startDate || !endDate)}
                    className="inline-flex items-center gap-2 px-8 py-3 bg-blue-600 text-white font-medium rounded-lg
                      hover:bg-blue-700 transition shadow-sm text-base disabled:opacity-50 disabled:cursor-not-allowed">
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" />
                    </svg>
                    Generate PDF
                  </button>
                  {printToPdf && (
                    <a
                      href={statementHtmlUrl(
                        bankId, accountSlug,
                        genMode === 'range' && startDate ? (() => { const [y,m,d] = startDate.split('-'); return `${d}/${m}/${y}`; })() : '',
                        genMode === 'range' && endDate ? (() => { const [y,m,d] = endDate.split('-'); return `${d}/${m}/${y}`; })() : ''
                      )}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 px-6 py-3 border-2 border-blue-600 text-blue-600 font-medium rounded-lg
                        hover:bg-blue-50 transition text-base">
                      <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6.72 13.829c-.24.03-.48.062-.72.096m.72-.096a42.415 42.415 0 0110.56 0m-10.56 0L6.34 18m10.94-4.171c.24.03.48.062.72.096m-.72-.096L17.66 18m0 0l.229 2.523a1.125 1.125 0 01-1.12 1.227H7.231c-.662 0-1.18-.568-1.12-1.227L6.34 18m11.318 0h1.091A2.25 2.25 0 0021 15.75V9.456c0-1.081-.768-2.015-1.837-2.175a48.055 48.055 0 00-1.913-.247M6.34 18H5.25A2.25 2.25 0 013 15.75V9.456c0-1.081.768-2.015 1.837-2.175a48.041 48.041 0 011.913-.247m10.5 0a48.536 48.536 0 00-10.5 0m10.5 0V3.375c0-.621-.504-1.125-1.125-1.125h-8.25c-.621 0-1.125.504-1.125 1.125v3.659M18.75 12h.008v.008h-.008V12z" />
                      </svg>
                      Save as PDF
                    </a>
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        {error && (
          <div className="px-6 py-3 bg-red-50 border-t border-red-100 flex items-center gap-2">
            <svg className="w-4 h-4 text-red-500 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
            <span className="text-xs text-red-700">{error}</span>
          </div>
        )}
      </div>

      <StatementHistory bankId={bankId} accountSlug={accountSlug} />
    </div>
  );
}
