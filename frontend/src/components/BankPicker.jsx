import { useState, useEffect, useRef } from 'react';
import { listBanks, onboardBank } from '../api';

const BANK_LOGOS = {
  hsbc: (
    <svg viewBox="0 0 40 40" className="w-full h-full">
      <rect width="40" height="40" rx="8" fill="#DB0011" />
      <path d="M8 12h10v6H8zM22 12h10v6H8zM8 22h10v6H8zM22 22h10v6H22z" fill="white" />
    </svg>
  ),
  default: (
    <svg viewBox="0 0 40 40" className="w-full h-full">
      <rect width="40" height="40" rx="8" fill="#6B7280" />
      <path d="M20 8l10 6v2H10v-2l10-6zm-8 10h4v10h-4zm6 0h4v10h-4zm6 0h4v10h-4zM10 30h20v2H10z" fill="white" />
    </svg>
  ),
};

export default function BankPicker({ onSelect }) {
  const [banks, setBanks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);

  // Add New Bank state
  const [showAddBank, setShowAddBank] = useState(false);
  const [newBankName, setNewBankName] = useState('');
  const [newBankFile, setNewBankFile] = useState(null);
  const [onboarding, setOnboarding] = useState(false);
  const [onboardResult, setOnboardResult] = useState(null);
  const [onboardError, setOnboardError] = useState('');
  const fileRef = useRef();

  useEffect(() => {
    loadBanks();
  }, []);

  function loadBanks() {
    setLoading(true);
    listBanks().then(data => {
      setBanks(data.banks || []);
      setLoading(false);
    });
  }

  function handleContinue() {
    if (selected) onSelect(selected.id);
  }

  async function handleOnboard() {
    if (!newBankFile || !newBankName.trim()) return;
    setOnboarding(true);
    setOnboardError('');
    setOnboardResult(null);

    try {
      const result = await onboardBank(newBankFile, newBankName.trim());
      setOnboardResult(result);
      // Reload banks list
      loadBanks();
    } catch (err) {
      setOnboardError(err.message || 'Onboarding failed');
    } finally {
      setOnboarding(false);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="flex items-center gap-3 text-gray-400">
          <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-sm">Loading banks...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl">
      <div className="grid grid-cols-2 gap-4">
        {banks.map(bank => (
          <button
            key={bank.id}
            onClick={() => { setSelected(bank); setShowAddBank(false); }}
            className={`flex items-center gap-4 p-5 rounded-xl border-2 text-left transition-all duration-150
              ${selected?.id === bank.id
                ? 'border-blue-500 bg-blue-50 ring-2 ring-blue-200 shadow-sm'
                : 'border-gray-200 bg-white hover:border-gray-300 hover:shadow-sm'
              }`}
          >
            <div className="w-12 h-12 shrink-0">
              {BANK_LOGOS[bank.id] || BANK_LOGOS.default}
            </div>
            <div>
              <div className="text-base font-semibold text-gray-900">{bank.name}</div>
              <div className="text-xs text-gray-500">{bank.full_name}</div>
            </div>
            {selected?.id === bank.id && (
              <svg className="w-5 h-5 text-blue-600 ml-auto shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
              </svg>
            )}
          </button>
        ))}

        {/* Add New Bank button */}
        <button
          onClick={() => { setShowAddBank(true); setSelected(null); }}
          className={`flex items-center gap-4 p-5 rounded-xl border-2 text-left transition-all duration-150
            ${showAddBank
              ? 'border-green-500 bg-green-50 ring-2 ring-green-200 shadow-sm'
              : 'border-dashed border-gray-300 bg-gray-50 hover:border-gray-400 hover:bg-white'
            }`}
        >
          <div className="w-12 h-12 shrink-0 rounded-lg bg-green-100 flex items-center justify-center">
            <svg className="w-6 h-6 text-green-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
          </div>
          <div>
            <div className="text-sm font-semibold text-gray-700">Add New Bank</div>
            <div className="text-xs text-gray-500">Upload a sample statement PDF</div>
          </div>
        </button>
      </div>

      {/* Add New Bank Form */}
      {showAddBank && (
        <div className="mt-6 p-6 bg-white border border-gray-200 rounded-xl shadow-sm animate-fade-in">
          <h3 className="text-sm font-semibold text-gray-900 mb-4">Add a New Bank Template</h3>
          <p className="text-xs text-gray-500 mb-4">
            Upload a sample bank statement PDF. The system will automatically detect the table layout,
            columns, fonts, and spacing — no manual calibration needed.
          </p>

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Bank Name</label>
              <input
                type="text"
                value={newBankName}
                onChange={e => setNewBankName(e.target.value)}
                placeholder="e.g., HDFC Bank, SBI, ICICI"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-green-200 focus:border-green-500 outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-700 mb-1">Sample Statement PDF</label>
              <div
                onClick={() => fileRef.current?.click()}
                className={`flex items-center gap-3 px-4 py-3 border-2 border-dashed rounded-lg cursor-pointer transition
                  ${newBankFile ? 'border-green-400 bg-green-50' : 'border-gray-300 hover:border-gray-400'}`}
              >
                <svg className={`w-5 h-5 ${newBankFile ? 'text-green-600' : 'text-gray-400'}`} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m6.75 12H9.75m0 0l2.25-2.25M9.75 14.25l2.25 2.25M6 20.25h12A2.25 2.25 0 0020.25 18V6.75A2.25 2.25 0 0018 4.5H6A2.25 2.25 0 003.75 6.75v11.25c0 1.243 1.007 2.25 2.25 2.25z" />
                </svg>
                <span className="text-sm text-gray-600">
                  {newBankFile ? newBankFile.name : 'Click to select PDF...'}
                </span>
              </div>
              <input
                ref={fileRef}
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={e => setNewBankFile(e.target.files[0] || null)}
              />
            </div>

            {onboardError && (
              <div className="text-xs text-red-600 bg-red-50 p-3 rounded-lg">{onboardError}</div>
            )}

            {onboardResult && (
              <div className="text-xs text-green-700 bg-green-50 p-3 rounded-lg">
                <div className="font-semibold mb-1">Bank "{onboardResult.bank_name}" added successfully!</div>
                <div>Columns detected: {onboardResult.columns_detected?.join(', ') || 'none'}</div>
                <div>Page size: {onboardResult.page_size}</div>
                <div className="mt-2 text-gray-600">You can now select it from the bank list above.</div>
              </div>
            )}

            <button
              onClick={handleOnboard}
              disabled={!newBankFile || !newBankName.trim() || onboarding}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-green-600 text-white font-medium rounded-lg
                hover:bg-green-700 active:bg-green-800 transition shadow-sm text-sm
                disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {onboarding ? (
                <>
                  <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Analyzing PDF...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                  </svg>
                  Add Bank
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Continue Button */}
      {selected && (
        <div className="mt-8 animate-fade-in">
          <button onClick={handleContinue}
            className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white font-medium rounded-lg
              hover:bg-blue-700 active:bg-blue-800 transition shadow-sm hover:shadow text-sm">
            Continue with {selected.name}
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}
