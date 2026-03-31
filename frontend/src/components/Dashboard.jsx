import { useState, useEffect } from 'react';
import { getDashboard, createAccount, deleteAccount } from '../api';

export default function Dashboard({ onOpenAccount, onNewBank }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});
  const [creating, setCreating] = useState(null); // bank_id being created under
  const [newName, setNewName] = useState('');
  const [newAccNum, setNewAccNum] = useState('');

  useEffect(() => { loadData(); }, []);

  async function loadData() {
    setLoading(true);
    const res = await getDashboard();
    setData(res);
    // Auto-expand all banks
    const exp = {};
    (res.banks || []).forEach(b => { exp[b.id] = true; });
    setExpanded(exp);
    setLoading(false);
  }

  function toggle(bankId) {
    setExpanded(prev => ({ ...prev, [bankId]: !prev[bankId] }));
  }

  async function handleCreate(bankId) {
    if (!newName.trim()) return;
    try {
      const res = await createAccount(bankId, {
        customer_name: newName.trim(),
        account_number: newAccNum.trim(),
      });
      setCreating(null);
      setNewName('');
      setNewAccNum('');
      loadData();
      onOpenAccount(bankId, res.account_slug);
    } catch (err) {
      alert(err.message);
    }
  }

  async function handleDelete(bankId, slug, name) {
    if (!confirm(`Delete account "${name || slug}"? This removes all data and statements.`)) return;
    try {
      await deleteAccount(bankId, slug);
      loadData();
    } catch (err) {
      alert(err.message);
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
          <span className="text-sm">Loading...</span>
        </div>
      </div>
    );
  }

  const banks = data?.banks || [];

  return (
    <div className="max-w-4xl">
      {banks.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-gray-400 text-lg mb-2">No banks set up yet</div>
          <p className="text-sm text-gray-400 mb-6">Add a bank template to get started</p>
          <button onClick={onNewBank}
            className="inline-flex items-center gap-2 px-6 py-3 bg-green-600 text-white font-medium rounded-lg hover:bg-green-700 transition text-sm">
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
            </svg>
            Add New Bank
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {banks.map(bank => (
            <div key={bank.id} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              {/* Bank header */}
              <button onClick={() => toggle(bank.id)}
                className="w-full flex items-center justify-between px-6 py-4 hover:bg-gray-50 transition">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center">
                    <svg className="w-5 h-5 text-blue-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 21v-8.25M15.75 21v-8.25M8.25 21v-8.25M3 9l9-6 9 6m-1.5 12V10.332A48.36 48.36 0 0012 9.75c-2.551 0-5.056.2-7.5.582V21" />
                    </svg>
                  </div>
                  <div className="text-left">
                    <div className="text-base font-semibold text-gray-900">{bank.name}</div>
                    <div className="text-xs text-gray-500">{bank.account_count} account{bank.account_count !== 1 ? 's' : ''}</div>
                  </div>
                </div>
                <svg className={`w-5 h-5 text-gray-400 transition-transform ${expanded[bank.id] ? 'rotate-180' : ''}`}
                  fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
                </svg>
              </button>

              {/* Accounts list */}
              {expanded[bank.id] && (
                <div className="border-t border-gray-100">
                  {bank.accounts.length === 0 && creating !== bank.id ? (
                    <div className="px-6 py-8 text-center text-sm text-gray-400">
                      No accounts yet
                    </div>
                  ) : (
                    <div className="divide-y divide-gray-50">
                      {bank.accounts.map(acct => (
                        <div key={acct.slug}
                          className="flex items-center justify-between px-6 py-3 hover:bg-gray-50 group">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center shrink-0">
                              <span className="text-xs font-bold text-gray-500">
                                {(acct.customer_name || acct.slug).charAt(0).toUpperCase()}
                              </span>
                            </div>
                            <div className="min-w-0">
                              <div className="text-sm font-medium text-gray-900 truncate">
                                {acct.customer_name || acct.slug}
                              </div>
                              <div className="text-xs text-gray-400 flex items-center gap-3">
                                {acct.account_number && <span>{acct.account_number}</span>}
                                <span>{acct.txn_count} txns</span>
                                <span>{acct.statement_count} statement{acct.statement_count !== 1 ? 's' : ''}</span>
                              </div>
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            <button onClick={() => onOpenAccount(bank.id, acct.slug)}
                              className="px-3 py-1.5 text-xs font-medium text-blue-600 bg-blue-50 rounded-lg
                                hover:bg-blue-100 transition opacity-0 group-hover:opacity-100">
                              Open
                            </button>
                            <button onClick={() => handleDelete(bank.id, acct.slug, acct.customer_name)}
                              className="px-2 py-1.5 text-xs text-red-400 rounded-lg hover:bg-red-50 hover:text-red-600
                                transition opacity-0 group-hover:opacity-100">
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
                              </svg>
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* New account form */}
                  {creating === bank.id ? (
                    <div className="px-6 py-4 bg-blue-50 border-t border-blue-100">
                      <div className="flex items-end gap-3">
                        <div className="flex-1">
                          <label className="block text-xs font-medium text-gray-700 mb-1">Customer Name</label>
                          <input type="text" value={newName} onChange={e => setNewName(e.target.value)}
                            placeholder="e.g., MR HARSHA REDDY" autoFocus
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-200" />
                        </div>
                        <div className="w-48">
                          <label className="block text-xs font-medium text-gray-700 mb-1">Account Number</label>
                          <input type="text" value={newAccNum} onChange={e => setNewAccNum(e.target.value)}
                            placeholder="Optional"
                            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-blue-200" />
                        </div>
                        <button onClick={() => handleCreate(bank.id)}
                          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition">
                          Create
                        </button>
                        <button onClick={() => { setCreating(null); setNewName(''); setNewAccNum(''); }}
                          className="px-3 py-2 text-sm text-gray-500 hover:text-gray-700">
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button onClick={() => setCreating(bank.id)}
                      className="w-full px-6 py-3 text-left text-sm text-blue-600 hover:bg-blue-50 transition
                        flex items-center gap-2 border-t border-gray-100">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                      </svg>
                      New Account
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}

          {/* Add new bank button */}
          <button onClick={onNewBank}
            className="w-full flex items-center gap-4 px-6 py-4 bg-white rounded-xl border-2 border-dashed border-gray-300
              hover:border-gray-400 hover:bg-gray-50 transition">
            <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center">
              <svg className="w-5 h-5 text-green-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
              </svg>
            </div>
            <div className="text-left">
              <div className="text-sm font-semibold text-gray-700">Add New Bank</div>
              <div className="text-xs text-gray-500">Set up a template for another bank</div>
            </div>
          </button>
        </div>
      )}
    </div>
  );
}
