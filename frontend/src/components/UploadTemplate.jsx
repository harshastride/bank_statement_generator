import { useState, useRef } from 'react';
import { uploadTemplate } from '../api';

export default function UploadTemplate({ jobId, onDone }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [dragOver, setDragOver] = useState(false);
  const [fileName, setFileName] = useState('');
  const inputRef = useRef();

  async function processFile(file) {
    if (!file || !file.name.toLowerCase().endsWith('.pdf')) {
      setError('Please select a valid PDF file.');
      return;
    }
    setFileName(file.name);
    setLoading(true);
    setError('');
    try {
      const res = await uploadTemplate(jobId, file);
      setResult(res);
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleDrop(e) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    processFile(file);
  }

  return (
    <div className="max-w-xl">
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {/* Drop Zone */}
        <div
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          onClick={() => !loading && inputRef.current?.click()}
          className={`relative p-10 text-center cursor-pointer transition-all duration-200
            ${dragOver
              ? 'bg-blue-50 border-2 border-dashed border-blue-400'
              : loading
                ? 'bg-gray-50'
                : 'hover:bg-gray-50'
            }`}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".pdf"
            onChange={e => processFile(e.target.files[0])}
            className="hidden"
            disabled={loading}
          />

          {loading ? (
            <div className="animate-fade-in">
              <div className="mx-auto w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center mb-4">
                <svg className="w-5 h-5 text-blue-600 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              </div>
              <p className="text-sm font-medium text-gray-900">Extracting template...</p>
              <p className="text-xs text-gray-500 mt-1">{fileName}</p>
              <div className="mt-4 mx-auto w-48 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div className="h-full bg-blue-500 rounded-full" style={{
                  animation: 'shimmer 1.5s infinite',
                  background: 'linear-gradient(90deg, #3b82f6 25%, #60a5fa 50%, #3b82f6 75%)',
                  backgroundSize: '200% 100%',
                }} />
              </div>
            </div>
          ) : result ? (
            <div className="animate-fade-in">
              <div className="mx-auto w-12 h-12 rounded-full bg-green-100 flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-green-600" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
              </div>
              <p className="text-sm font-medium text-green-700">Template extracted successfully</p>
              <p className="text-xs text-gray-500 mt-1">{fileName}</p>
            </div>
          ) : (
            <>
              <div className="mx-auto w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center mb-4">
                <svg className="w-6 h-6 text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
                </svg>
              </div>
              <p className="text-sm font-medium text-gray-700">
                Drop your PDF here, or <span className="text-blue-600">browse</span>
              </p>
              <p className="text-xs text-gray-400 mt-1">
                Upload an existing bank statement to extract its layout
              </p>
            </>
          )}
        </div>

        {/* Result Details */}
        {result && (
          <div className="px-6 py-4 bg-gray-50 border-t border-gray-100">
            <div className="flex items-center gap-6 text-xs text-gray-500">
              <div className="flex items-center gap-1.5">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
                {Math.round(result.page_width)} x {Math.round(result.page_height)} pt
              </div>
              {result.has_footer && (
                <div className="flex items-center gap-1.5">
                  <svg className="w-3.5 h-3.5 text-green-500" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Footer detected
                </div>
              )}
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="px-6 py-3 bg-red-50 border-t border-red-100 flex items-center gap-2 animate-fade-in">
            <svg className="w-4 h-4 text-red-500 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
            <span className="text-xs text-red-700">{error}</span>
          </div>
        )}
      </div>
    </div>
  );
}
