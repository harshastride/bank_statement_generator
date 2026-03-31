import { useState } from 'react';
import Sidebar from './components/Sidebar';
import Dashboard from './components/Dashboard';
import AccountForm from './components/AccountForm';
import TransactionsEditor from './components/TransactionsEditor';
import GenerateDownload from './components/GenerateDownload';
import NewBankSetup from './components/NewBankSetup';

const STEPS = [
  { id: 1, label: 'Account Details', icon: 'user',     desc: 'Edit metadata' },
  { id: 2, label: 'Transactions',    icon: 'table',    desc: 'Manage entries' },
  { id: 3, label: 'Generate PDF',    icon: 'download', desc: 'Build & download' },
];

export default function App() {
  const [mode, setMode] = useState('dashboard'); // 'dashboard' | 'wizard' | 'setup'
  const [bankId, setBankId] = useState(null);
  const [accountSlug, setAccountSlug] = useState(null);
  const [step, setStep] = useState(1);
  const [completed, setCompleted] = useState([]);
  const [transactions, setTransactions] = useState([]);

  function completeStep(n) {
    setCompleted(prev => [...new Set([...prev, n])]);
    setStep(n + 1);
  }

  function goToStep(n) {
    if (n === 1 || completed.includes(n - 1)) setStep(n);
  }

  function openAccount(bId, slug) {
    setBankId(bId);
    setAccountSlug(slug);
    setStep(1);
    setCompleted([]);
    setMode('wizard');
  }

  function goToDashboard() {
    setMode('dashboard');
    setBankId(null);
    setAccountSlug(null);
    setStep(1);
    setCompleted([]);
  }

  function goToSetup() {
    setMode('setup');
  }

  return (
    <div className="min-h-screen flex bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col min-h-screen shrink-0">
        {/* Logo */}
        <div className="px-6 py-5 border-b border-gray-100">
          <button onClick={goToDashboard} className="flex items-center gap-2.5 hover:opacity-80 transition">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-600 to-blue-700 flex items-center justify-center">
              <svg className="w-4 h-4 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
            </div>
            <div>
              <div className="text-sm font-semibold text-gray-900">StatementGen</div>
              <div className="text-[11px] text-gray-400">PDF Builder</div>
            </div>
          </button>
        </div>

        {/* Mode Switcher */}
        <div className="px-3 py-3 border-b border-gray-100">
          <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5">
            <button onClick={goToDashboard}
              className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition
                ${mode === 'dashboard' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
              Dashboard
            </button>
            <button onClick={goToSetup}
              className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition
                ${mode === 'setup' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'}`}>
              New Bank
            </button>
          </div>
        </div>

        {/* Sidebar content per mode */}
        {mode === 'wizard' ? (
          <>
            {/* Back to dashboard */}
            <div className="px-3 pt-3">
              <button onClick={goToDashboard}
                className="flex items-center gap-2 px-3 py-2 text-xs text-gray-500 hover:text-gray-700 transition w-full rounded-lg hover:bg-gray-50">
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
                </svg>
                Back to Dashboard
              </button>
            </div>
            {/* Bank + account info */}
            <div className="px-3 py-2">
              <div className="px-3 py-2.5 rounded-lg bg-blue-50">
                <div className="text-xs font-medium text-blue-700">{bankId?.toUpperCase()}</div>
                <div className="text-[11px] text-blue-500 truncate">{accountSlug}</div>
              </div>
            </div>
            <Sidebar
              steps={STEPS}
              current={step}
              completed={completed}
              onNavigate={goToStep}
            />
            {/* Progress */}
            <div className="mt-auto px-4 py-4 border-t border-gray-100">
              <div className="text-[11px] text-gray-400 text-center">
                {completed.length} of {STEPS.length} steps complete
              </div>
              <div className="mt-2 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-blue-500 to-blue-600 rounded-full transition-all duration-500"
                  style={{ width: `${(completed.length / STEPS.length) * 100}%` }}
                />
              </div>
            </div>
          </>
        ) : mode === 'setup' ? (
          <nav className="flex-1 px-3 py-4">
            <div className="px-3 py-2.5 rounded-lg bg-green-50 text-green-700">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-green-600 text-white flex items-center justify-center shrink-0 shadow-sm">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.75} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 21v-8.25M15.75 21v-8.25M8.25 21v-8.25M3 9l9-6 9 6m-1.5 12V10.332A48.36 48.36 0 0012 9.75c-2.551 0-5.056.2-7.5.582V21" />
                  </svg>
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-medium">New Bank Setup</div>
                  <div className="text-[11px] text-green-500">Add any bank template</div>
                </div>
              </div>
            </div>
          </nav>
        ) : (
          <nav className="flex-1 px-3 py-4">
            <div className="px-3 py-2.5 rounded-lg bg-blue-50 text-blue-700">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center shrink-0 shadow-sm">
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.75} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
                  </svg>
                </div>
                <div className="min-w-0">
                  <div className="text-sm font-medium">Dashboard</div>
                  <div className="text-[11px] text-blue-500">All banks & accounts</div>
                </div>
              </div>
            </div>
          </nav>
        )}
      </aside>

      {/* Main Content */}
      <main className="flex-1 min-h-screen overflow-y-auto">
        <div className="max-w-5xl mx-auto px-6 py-8 lg:px-10">
          {/* Page Header */}
          <div className="mb-8 animate-fade-in">
            {mode === 'wizard' ? (
              <>
                <h1 className="text-2xl font-semibold text-gray-900">{STEPS[step - 1].label}</h1>
                <p className="text-sm text-gray-500 mt-1">
                  {step === 1 && 'Review and edit the account holder information.'}
                  {step === 2 && 'Manage transactions — add, edit, or import from CSV.'}
                  {step === 3 && 'Generate the final PDF statement and download it.'}
                </p>
              </>
            ) : mode === 'setup' ? (
              <>
                <h1 className="text-2xl font-semibold text-gray-900">New Bank Setup</h1>
                <p className="text-sm text-gray-500 mt-1">
                  Add support for any bank by uploading a sample statement and using Claude to extract the layout.
                </p>
              </>
            ) : (
              <>
                <h1 className="text-2xl font-semibold text-gray-900">Dashboard</h1>
                <p className="text-sm text-gray-500 mt-1">
                  All your banks and accounts. Click an account to edit or generate statements.
                </p>
              </>
            )}
          </div>

          {/* Content */}
          {mode === 'dashboard' && (
            <div className="animate-slide-up" key="dashboard">
              <Dashboard onOpenAccount={openAccount} onNewBank={goToSetup} />
            </div>
          )}

          {mode === 'wizard' && bankId && accountSlug && (
            <div className="animate-slide-up" key={`${bankId}-${accountSlug}-${step}`}>
              {step === 1 && (
                <AccountForm bankId={bankId} accountSlug={accountSlug} onDone={() => completeStep(1)} />
              )}
              {step === 2 && (
                <TransactionsEditor
                  bankId={bankId} accountSlug={accountSlug}
                  onDone={() => completeStep(2)}
                  onRowsChange={setTransactions}
                />
              )}
              {step === 3 && (
                <GenerateDownload
                  bankId={bankId} accountSlug={accountSlug}
                  transactions={transactions}
                />
              )}
            </div>
          )}

          {mode === 'setup' && (
            <div className="animate-slide-up" key="setup">
              <NewBankSetup />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
