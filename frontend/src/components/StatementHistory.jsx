import { useState, useEffect } from 'react';
import { listStatements, statementDownloadUrl } from '../api';

export default function StatementHistory({ bankId, accountSlug }) {
  const [statements, setStatements] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStatements();
  }, [bankId, accountSlug]);

  async function loadStatements() {
    setLoading(true);
    try {
      const res = await listStatements(bankId, accountSlug);
      setStatements(res.statements || []);
    } catch (err) {
      console.error('Failed to load statements:', err);
    }
    setLoading(false);
  }

  if (loading) return null;
  if (statements.length === 0) return null;

  return (
    <div className="mt-6 bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-100">
        <h3 className="text-sm font-semibold text-gray-900">Generated Statements</h3>
      </div>
      <div className="divide-y divide-gray-50">
        {statements.map(stmt => (
          <div key={stmt.filename} className="flex items-center justify-between px-5 py-3 hover:bg-gray-50 group">
            <div className="flex items-center gap-3">
              <svg className="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
              <div>
                <div className="text-sm font-medium text-gray-800">{stmt.filename}</div>
                <div className="text-xs text-gray-400">
                  {(stmt.size / 1024).toFixed(1)} KB
                  {stmt.created && ` \u00b7 ${new Date(stmt.created).toLocaleDateString()}`}
                </div>
              </div>
            </div>
            <a href={statementDownloadUrl(bankId, accountSlug, stmt.filename)}
              download={stmt.filename}
              className="px-3 py-1.5 text-xs font-medium text-blue-600 bg-blue-50 rounded-lg
                hover:bg-blue-100 transition opacity-0 group-hover:opacity-100">
              Download
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}
