'use client';

import { useState, useEffect, useCallback } from 'react';
import { api, login, getToken, clearToken } from '@/lib/api';
import {
  LineChart, Line, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';

// ── Login Screen ─────────────────────────────────────────────────────────

function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await login(username, password);
      onLogin();
    } catch {
      setError('Invalid credentials');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="card w-full max-w-sm">
        <h1 className="text-2xl font-bold mb-6 text-center">FX Trading System</h1>
        <form onSubmit={handleSubmit} className="space-y-4">
          <input
            type="text"
            placeholder="Username"
            value={username}
            onChange={e => setUsername(e.target.value)}
            className="w-full px-4 py-2 rounded-lg bg-primary border border-gray-700 focus:outline-none focus:border-blue-500"
          />
          <input
            type="password"
            placeholder="Password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            className="w-full px-4 py-2 rounded-lg bg-primary border border-gray-700 focus:outline-none focus:border-blue-500"
          />
          {error && <p className="text-danger text-sm">{error}</p>}
          <button type="submit" className="btn-primary w-full">Login</button>
        </form>
      </div>
    </div>
  );
}

// ── Stat Card ────────────────────────────────────────────────────────────

function StatCard({ label, value, color = '#e0e0e0', prefix = '' }: {
  label: string; value: string | number; color?: string; prefix?: string;
}) {
  return (
    <div className="card">
      <p className="stat-label">{label}</p>
      <p className="stat-value" style={{ color }}>{prefix}{value}</p>
    </div>
  );
}

// ── Main Dashboard ──────────────────────────────────────────────────────

function Dashboard() {
  const [activeTab, setActiveTab] = useState('overview');
  const [status, setStatus] = useState<any>(null);
  const [performance, setPerformance] = useState<any>(null);
  const [balance, setBalance] = useState<any>(null);
  const [liveAccount, setLiveAccount] = useState<any>(null);
  const [trades, setTrades] = useState<any[]>([]);
  const [positions, setPositions] = useState<any[]>([]);
  const [logs, setLogs] = useState<any[]>([]);
  const [strategies, setStrategies] = useState<any[]>([]);
  const [metaDecisions, setMetaDecisions] = useState<any[]>([]);
  const [rankings, setRankings] = useState<any[]>([]);
  const [sessionInfo, setSessionInfo] = useState<any>(null);
  const [balanceHistory, setBalanceHistory] = useState<any[]>([]);
  const [newsConfig, setNewsConfig] = useState<any>(null);

  const fetchData = useCallback(async () => {
    try {
      const [s, p, b, t, pos, str] = await Promise.all([
        api.getStatus(),
        api.getPerformance(),
        api.getBalance(),
        api.getTrades('limit=50'),
        api.getPositions(),
        api.getStrategies(),
      ]);
      setStatus(s);
      setPerformance(p);
      setBalance(b);
      setTrades(t);
      setPositions(pos);
      setStrategies(str);

      try {
        const nc = await api.getNewsConfig();
        setNewsConfig(nc);
      } catch {
        // Optional endpoint; keep dashboard usable even if unavailable.
      }

      // Fetch live MT5 account (may 404 if not available yet)
      try {
        const live = await api.getLiveAccount();
        setLiveAccount(live);
      } catch { /* not available yet */ }

      // Build equity curve from closed trades
      const closed = t.filter((tr: any) => tr.status === 'CLOSED' && tr.pnl != null);
      if (closed.length > 0) {
        let cumPnl = 0;
        const curve = closed.reverse().map((tr: any, i: number) => {
          cumPnl += tr.pnl;
          return { name: `#${i + 1}`, equity: parseFloat(cumPnl.toFixed(2)) };
        });
        setBalanceHistory(curve);
      }
    } catch (err) {
      console.error('Fetch error:', err);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleBotControl = async (action: string) => {
    try {
      await api.controlBot(action);
      await fetchData();
    } catch (err) {
      console.error('Control error:', err);
    }
  };

  const handleNewsManualToggle = async (enabled: boolean) => {
    try {
      await api.setNewsManualSource(enabled);
      const nc = await api.getNewsConfig();
      setNewsConfig(nc);
    } catch (err) {
      console.error('News toggle error:', err);
    }
  };

  const fetchLogs = async () => {
    try {
      const l = await api.getLogs(200);
      setLogs(l);
    } catch (err) {
      console.error('Logs error:', err);
    }
  };

  useEffect(() => {
    if (activeTab === 'logs') fetchLogs();
    if (activeTab === 'meta') fetchMetaData();
  }, [activeTab]);

  const fetchMetaData = async () => {
    try {
      const [decisions, ranks, sess] = await Promise.all([
        api.getMetaDecisions(),
        api.getStrategyRankings(30),
        api.getSession(),
      ]);
      setMetaDecisions(decisions);
      setRankings(ranks);
      setSessionInfo(sess);
    } catch (err) {
      console.error('Meta fetch error:', err);
    }
  };

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'account', label: 'MT5 Account' },
    { id: 'positions', label: 'Positions' },
    { id: 'history', label: 'Trade History' },
    { id: 'meta', label: 'Meta-Strategy' },
    { id: 'strategies', label: 'Strategies' },
    { id: 'logs', label: 'Logs' },
  ];

  const pnlData = trades
    .filter((t: any) => t.status === 'CLOSED' && t.pnl !== null)
    .slice(0, 30)
    .reverse()
    .map((t: any, i: number) => ({ name: `#${i + 1}`, pnl: t.pnl }));

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-gray-800 px-6 py-4 flex justify-between items-center">
        <div>
          <h1 className="text-xl font-bold">FX Trading Dashboard</h1>
          <span className={`text-sm ${status?.status === 'RUNNING' ? 'text-green-400' : 'text-red-400'}`}>
            ● {status?.status || 'Loading...'}
          </span>
        </div>
        <div className="flex gap-2">
          <button onClick={() => handleBotControl('start')} className="btn-success text-sm">Start</button>
          <button onClick={() => handleBotControl('stop')} className="btn-danger text-sm">Stop</button>
          <button onClick={() => { clearToken(); window.location.reload(); }}
                  className="btn-primary text-sm ml-4">Logout</button>
        </div>
      </header>

      {/* Tabs */}
      <nav className="px-6 py-3 flex gap-4 border-b border-gray-800">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'bg-accent text-white'
                : 'text-gray-400 hover:text-white hover:bg-gray-800'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <main className="p-6">
        {activeTab === 'overview' && (
          <div className="space-y-6">
            {/* Stats Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
              <StatCard label="Balance" value={balance?.balance?.toFixed(2) || '0.00'} prefix="$" />
              <StatCard label="Equity" value={balance?.equity?.toFixed(2) || '0.00'} prefix="$" />
              <StatCard label="Daily P&L" value={balance?.daily_pnl?.toFixed(2) || '0.00'}
                        color={balance?.daily_pnl >= 0 ? '#00ff88' : '#ff4444'} prefix="$" />
              <StatCard label="Open Trades" value={balance?.open_positions || 0} color="#00aaff" />
              <StatCard label="Win Rate" value={`${((performance?.win_rate || 0) * 100).toFixed(1)}%`}
                        color={performance?.win_rate >= 0.5 ? '#00ff88' : '#ffaa00'} />
              <StatCard label="Total P&L" value={performance?.total_pnl?.toFixed(2) || '0.00'}
                        color={performance?.total_pnl >= 0 ? '#00ff88' : '#ff4444'} prefix="$" />
            </div>

            {/* Live MT5 Connection Banner */}
            {liveAccount && (
              <div className="card border border-green-800/50 bg-green-900/10">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span className="w-3 h-3 bg-green-400 rounded-full animate-pulse" />
                    <span className="font-medium text-green-400">MT5 Connected</span>
                    <span className="text-gray-500 text-sm">|</span>
                    <span className="text-sm text-gray-400">
                      Server: <span className="text-gray-200">{liveAccount.server}</span>
                    </span>
                    <span className="text-sm text-gray-400">
                      Account: <span className="text-gray-200">{liveAccount.login}</span>
                    </span>
                    <span className="text-sm text-gray-400">
                      Name: <span className="text-gray-200">{liveAccount.name}</span>
                    </span>
                  </div>
                  <span className="text-sm font-mono text-green-400">
                    Leverage 1:{liveAccount.leverage}
                  </span>
                </div>
              </div>
            )}

            {/* Charts Row */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Equity Curve */}
              <div className="card">
                <h3 className="text-sm font-medium text-gray-400 mb-4">Equity Curve (Cumulative P&L)</h3>
                {balanceHistory.length > 0 ? (
                  <ResponsiveContainer width="100%" height={250}>
                    <AreaChart data={balanceHistory}>
                      <defs>
                        <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#00aaff" stopOpacity={0.3}/>
                          <stop offset="95%" stopColor="#00aaff" stopOpacity={0}/>
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                      <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#888' }} />
                      <YAxis tick={{ fontSize: 10, fill: '#888' }} />
                      <Tooltip
                        contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #333' }}
                        labelStyle={{ color: '#ccc' }}
                      />
                      <Area type="monotone" dataKey="equity" stroke="#00aaff" fill="url(#equityGrad)"
                            name="Cumulative P&L" isAnimationActive={false} />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="text-center text-gray-500 py-12">No closed trades yet</p>
                )}
              </div>

              {/* P&L per Trade */}
              <div className="card">
                <h3 className="text-sm font-medium text-gray-400 mb-4">P&L per Trade</h3>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={pnlData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                    <XAxis dataKey="name" tick={{ fontSize: 10, fill: '#888' }} />
                    <YAxis tick={{ fontSize: 10, fill: '#888' }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#1a1a2e', border: '1px solid #333' }}
                      labelStyle={{ color: '#ccc' }}
                    />
                    <Bar dataKey="pnl" fill="#00aaff"
                         name="P&L"
                         isAnimationActive={false} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Performance + System Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div className="card">
                <h3 className="text-sm font-medium text-gray-400 mb-4">Performance Summary</h3>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="stat-label">Total Trades</p>
                    <p className="text-xl font-bold">{performance?.total_trades || 0}</p>
                  </div>
                  <div>
                    <p className="stat-label">Wins / Losses</p>
                    <p className="text-xl font-bold">
                      <span className="text-green-400">{performance?.wins || 0}</span>
                      {' / '}
                      <span className="text-red-400">{performance?.losses || 0}</span>
                    </p>
                  </div>
                  <div>
                    <p className="stat-label">Avg P&L</p>
                    <p className="text-xl font-bold">${performance?.avg_pnl?.toFixed(2) || '0.00'}</p>
                  </div>
                  <div>
                    <p className="stat-label">Max Drawdown</p>
                    <p className="text-xl font-bold text-red-400">
                      {((performance?.max_drawdown || 0) * 100).toFixed(1)}%
                    </p>
                  </div>
                </div>
              </div>

              <div className="card">
                <h3 className="text-sm font-medium text-gray-400 mb-3">System Information</h3>
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-500">Uptime: </span>
                    {status ? formatUptime(status.uptime_seconds) : '-'}
                  </div>
                  <div>
                    <span className="text-gray-500">Active Pairs: </span>
                    {status?.active_pairs?.length || 0}
                  </div>
                  <div>
                    <span className="text-gray-500">Strategies: </span>
                    {status?.strategies_active || 0}
                  </div>
                  <div>
                    <span className="text-gray-500">ML Models: </span>
                    {status?.ml_models_loaded || 0}
                  </div>
                  <div>
                    <span className="text-gray-500">Last Scan: </span>
                    {status?.last_scan ? formatDate(status.last_scan) : 'N/A'}
                  </div>
                  <div>
                    <span className="text-gray-500">Free Margin: </span>
                    ${balance?.free_margin?.toFixed(2) || '0.00'}
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t border-gray-800">
                  <h4 className="text-sm font-medium text-gray-400 mb-2">News Manual Source</h4>
                  <p className="text-xs text-gray-500 mb-3">
                    Toggle manual `NEWS_EVENTS_UTC` source without restarting. Auto feed stays active.
                  </p>
                  <div className="flex items-center gap-2 mb-2">
                    <button
                      onClick={() => handleNewsManualToggle(true)}
                      className="btn-success text-xs"
                      disabled={newsConfig?.enable_news_events_utc === true}
                    >
                      Enable Manual UTC
                    </button>
                    <button
                      onClick={() => handleNewsManualToggle(false)}
                      className="btn-danger text-xs"
                      disabled={newsConfig?.enable_news_events_utc === false}
                    >
                      Disable Manual UTC
                    </button>
                  </div>
                  {newsConfig && (
                    <p className="text-xs text-gray-400">
                      Manual UTC: <span className={newsConfig.enable_news_events_utc ? 'text-green-400' : 'text-red-400'}>
                        {newsConfig.enable_news_events_utc ? 'ON' : 'OFF'}
                      </span>
                      {' '}| Auto feed: <span className={newsConfig.enable_news_auto_update ? 'text-green-400' : 'text-red-400'}>
                        {newsConfig.enable_news_auto_update ? 'ON' : 'OFF'}
                      </span>
                      {' '}| Events loaded: {newsConfig.manual_events_count ?? 0}
                    </p>
                  )}
                </div>
              </div>
            </div>

            {/* Active Pairs */}
            {status?.active_pairs?.length > 0 && (
              <div className="card">
                <h3 className="text-sm font-medium text-gray-400 mb-3">Active Trading Pairs</h3>
                <div className="flex flex-wrap gap-2">
                  {status.active_pairs.map((pair: string) => (
                    <span key={pair} className="px-3 py-1 bg-blue-900/30 text-blue-300 rounded-full text-sm font-mono">
                      {pair}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── MT5 Account Tab ─────────────────────────────────────── */}
        {activeTab === 'account' && (
          <div className="space-y-6">
            {liveAccount ? (
              <>
                {/* Connection Card */}
                <div className="card border border-green-800/50">
                  <div className="flex items-center gap-3 mb-4">
                    <span className="w-4 h-4 bg-green-400 rounded-full animate-pulse" />
                    <h3 className="text-lg font-bold text-green-400">MT5 Connected</h3>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                    <div>
                      <p className="stat-label">Account Name</p>
                      <p className="text-lg font-bold">{liveAccount.name || 'N/A'}</p>
                    </div>
                    <div>
                      <p className="stat-label">Login</p>
                      <p className="text-lg font-bold font-mono">{liveAccount.login}</p>
                    </div>
                    <div>
                      <p className="stat-label">Server</p>
                      <p className="text-lg font-bold">{liveAccount.server}</p>
                    </div>
                    <div>
                      <p className="stat-label">Leverage</p>
                      <p className="text-lg font-bold">1:{liveAccount.leverage}</p>
                    </div>
                  </div>
                </div>

                {/* Balance Cards */}
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                  <StatCard label="Balance" value={(liveAccount.balance || 0).toFixed(2)} prefix="$" />
                  <StatCard label="Equity" value={(liveAccount.equity || 0).toFixed(2)} prefix="$" />
                  <StatCard label="Profit" value={(liveAccount.profit || 0).toFixed(2)}
                            color={liveAccount.profit >= 0 ? '#00ff88' : '#ff4444'} prefix="$" />
                  <StatCard label="Margin" value={(liveAccount.margin || 0).toFixed(2)} prefix="$" />
                  <StatCard label="Free Margin" value={(liveAccount.free_margin || 0).toFixed(2)} prefix="$" color="#00aaff" />
                  <StatCard label="Margin Level"
                            value={liveAccount.margin_level ? `${liveAccount.margin_level.toFixed(0)}%` : '∞'}
                            color={liveAccount.margin_level > 200 ? '#00ff88' : liveAccount.margin_level > 100 ? '#ffaa00' : '#ff4444'} />
                </div>

                {/* Margin Utilization Bar */}
                <div className="card">
                  <h3 className="text-sm font-medium text-gray-400 mb-3">Margin Utilization</h3>
                  <div className="w-full bg-gray-800 rounded-full h-6 overflow-hidden">
                    {(() => {
                      const used = liveAccount.margin || 0;
                      const total = (liveAccount.margin || 0) + (liveAccount.free_margin || 1);
                      const pct = Math.min((used / total) * 100, 100);
                      const color = pct < 30 ? 'bg-green-500' : pct < 60 ? 'bg-yellow-500' : 'bg-red-500';
                      return (
                        <div className={`h-6 ${color} rounded-full flex items-center justify-center text-xs font-bold text-black`}
                             style={{ width: `${Math.max(pct, 5)}%` }}>
                          {pct.toFixed(1)}%
                        </div>
                      );
                    })()}
                  </div>
                  <p className="text-xs text-gray-500 mt-2">
                    Used: ${(liveAccount.margin || 0).toFixed(2)} / Available: ${(liveAccount.free_margin || 0).toFixed(2)}
                  </p>
                </div>
              </>
            ) : (
              <div className="card text-center py-12">
                <span className="w-4 h-4 bg-red-500 rounded-full inline-block mb-3" />
                <p className="text-lg font-medium text-red-400">MT5 Not Connected</p>
                <p className="text-gray-500 mt-2">
                  Make sure MetaTrader 5 is running and the bot has started successfully.
                </p>
              </div>
            )}
          </div>
        )}

        {activeTab === 'positions' && (
          <div className="card">
            <h3 className="font-medium mb-4">Open Positions ({positions.length})</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-700 text-gray-400">
                    <th className="text-left py-2 px-3">Symbol</th>
                    <th className="text-left py-2 px-3">Type</th>
                    <th className="text-left py-2 px-3">Strategy</th>
                    <th className="text-right py-2 px-3">Entry</th>
                    <th className="text-right py-2 px-3">SL</th>
                    <th className="text-right py-2 px-3">TP</th>
                    <th className="text-right py-2 px-3">Lots</th>
                    <th className="text-right py-2 px-3">Risk %</th>
                    <th className="text-right py-2 px-3">Confidence</th>
                    <th className="text-left py-2 px-3">Regime</th>
                    <th className="text-left py-2 px-3">Opened</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((pos: any) => (
                    <tr key={pos.id} className="table-row">
                      <td className="py-2 px-3 font-medium">{pos.symbol}</td>
                      <td className="py-2 px-3">
                        <span className={pos.order_type === 'BUY' ? 'badge badge-buy' : 'badge badge-sell'}>
                          {pos.order_type}
                        </span>
                      </td>
                      <td className="py-2 px-3">{pos.strategy}</td>
                      <td className="py-2 px-3 text-right font-mono">{pos.entry_price?.toFixed(5)}</td>
                      <td className="py-2 px-3 text-right font-mono text-red-400">{pos.stop_loss?.toFixed(5)}</td>
                      <td className="py-2 px-3 text-right font-mono text-green-400">{pos.take_profit?.toFixed(5)}</td>
                      <td className="py-2 px-3 text-right">{pos.lot_size}</td>
                      <td className="py-2 px-3 text-right">{pos.risk_percent?.toFixed(1)}%</td>
                      <td className="py-2 px-3 text-right">{(pos.signal_confidence * 100)?.toFixed(0)}%</td>
                      <td className="py-2 px-3 text-xs">{pos.market_regime}</td>
                      <td className="py-2 px-3 text-xs text-gray-400">{formatDate(pos.opened_at)}</td>
                    </tr>
                  ))}
                  {positions.length === 0 && (
                    <tr><td colSpan={11} className="py-8 text-center text-gray-500">No open positions</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'history' && (
          <div className="card">
            <h3 className="font-medium mb-4">Trade History</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-700 text-gray-400">
                    <th className="text-left py-2 px-3">ID</th>
                    <th className="text-left py-2 px-3">Symbol</th>
                    <th className="text-left py-2 px-3">Type</th>
                    <th className="text-left py-2 px-3">Strategy</th>
                    <th className="text-left py-2 px-3">Status</th>
                    <th className="text-right py-2 px-3">Entry</th>
                    <th className="text-right py-2 px-3">Exit</th>
                    <th className="text-right py-2 px-3">Lots</th>
                    <th className="text-right py-2 px-3">P&L</th>
                    <th className="text-right py-2 px-3">Pips</th>
                    <th className="text-left py-2 px-3">Opened</th>
                    <th className="text-left py-2 px-3">Closed</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((trade: any) => (
                    <tr key={trade.id} className="table-row">
                      <td className="py-2 px-3">{trade.id}</td>
                      <td className="py-2 px-3 font-medium">{trade.symbol}</td>
                      <td className="py-2 px-3">
                        <span className={trade.order_type === 'BUY' ? 'badge badge-buy' : 'badge badge-sell'}>
                          {trade.order_type}
                        </span>
                      </td>
                      <td className="py-2 px-3">{trade.strategy}</td>
                      <td className="py-2 px-3">
                        <span className={trade.status === 'OPEN' ? 'badge badge-open' : 'badge badge-closed'}>
                          {trade.status}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-right font-mono">{trade.entry_price?.toFixed(5)}</td>
                      <td className="py-2 px-3 text-right font-mono">{trade.exit_price?.toFixed(5) || '-'}</td>
                      <td className="py-2 px-3 text-right">{trade.lot_size}</td>
                      <td className={`py-2 px-3 text-right font-medium ${
                        trade.pnl > 0 ? 'text-green-400' : trade.pnl < 0 ? 'text-red-400' : ''
                      }`}>
                        {trade.pnl != null ? `$${trade.pnl.toFixed(2)}` : '-'}
                      </td>
                      <td className="py-2 px-3 text-right">{trade.pnl_pips?.toFixed(1) || '-'}</td>
                      <td className="py-2 px-3 text-xs text-gray-400">{formatDate(trade.opened_at)}</td>
                      <td className="py-2 px-3 text-xs text-gray-400">{trade.closed_at ? formatDate(trade.closed_at) : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'meta' && (
          <div className="space-y-6">
            {/* Session Info */}
            {sessionInfo && (
              <div className="card">
                <h3 className="font-medium mb-3">Market Session</h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                  <div>
                    <span className="text-gray-500">Active Sessions: </span>
                    <span className="font-medium">
                      {sessionInfo.active_sessions?.length > 0
                        ? sessionInfo.active_sessions.join(', ')
                        : 'None'}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">Overlap: </span>
                    <span className={sessionInfo.is_overlap ? 'text-yellow-400' : 'text-gray-400'}>
                      {sessionInfo.is_overlap ? sessionInfo.overlap_sessions?.join(', ') : 'No'}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">Volatility: </span>
                    <span className={
                      sessionInfo.volatility_expectation === 'HIGH' ? 'text-red-400 font-medium'
                        : sessionInfo.volatility_expectation === 'MEDIUM' ? 'text-yellow-400'
                        : 'text-gray-400'
                    }>
                      {sessionInfo.volatility_expectation}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">Best Pairs: </span>
                    <span className="text-xs">{sessionInfo.best_pairs?.join(', ') || '-'}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Strategy Rankings */}
            <div className="card">
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-medium">Strategy Performance Rankings</h3>
                <button onClick={fetchMetaData} className="btn-primary text-sm">Refresh</button>
              </div>
              {rankings.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-700 text-gray-400">
                        <th className="text-left py-2 px-3">#</th>
                        <th className="text-left py-2 px-3">Strategy</th>
                        <th className="text-right py-2 px-3">Trades</th>
                        <th className="text-right py-2 px-3">Win Rate</th>
                        <th className="text-right py-2 px-3">P&L</th>
                        <th className="text-right py-2 px-3">Avg P&L</th>
                        <th className="text-right py-2 px-3">Profit Factor</th>
                        <th className="text-right py-2 px-3">Sharpe</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rankings.map((r: any, i: number) => (
                        <tr key={r.strategy} className="table-row">
                          <td className="py-2 px-3 text-gray-500">{i + 1}</td>
                          <td className="py-2 px-3 font-medium">{r.strategy}</td>
                          <td className="py-2 px-3 text-right">{r.total_trades}</td>
                          <td className="py-2 px-3 text-right">
                            <span className={r.win_rate >= 0.5 ? 'text-green-400' : 'text-red-400'}>
                              {(r.win_rate * 100).toFixed(1)}%
                            </span>
                          </td>
                          <td className={`py-2 px-3 text-right font-medium ${
                            r.total_pnl > 0 ? 'text-green-400' : 'text-red-400'
                          }`}>
                            ${r.total_pnl?.toFixed(2)}
                          </td>
                          <td className="py-2 px-3 text-right">${r.avg_pnl?.toFixed(2)}</td>
                          <td className="py-2 px-3 text-right">{r.profit_factor?.toFixed(2)}</td>
                          <td className="py-2 px-3 text-right">{r.sharpe?.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-center text-gray-500 py-6">No strategy performance data yet. Trades must be closed to generate rankings.</p>
              )}
            </div>

            {/* Meta-Strategy Decisions */}
            <div className="card">
              <h3 className="font-medium mb-4">Latest Meta-Strategy Decisions</h3>
              {metaDecisions.length > 0 ? (
                <div className="space-y-4">
                  {metaDecisions.map((d: any) => (
                    <div key={d.symbol} className="border border-gray-700 rounded-lg p-4">
                      <div className="flex justify-between items-start mb-3">
                        <div>
                          <span className="font-bold text-lg">{d.symbol}</span>
                          <span className="ml-3 text-sm px-2 py-0.5 rounded bg-blue-900/40 text-blue-300">
                            {d.regime}
                          </span>
                        </div>
                        <span className="text-sm text-gray-400">
                          Confidence: <span className={d.confidence >= 0.5 ? 'text-green-400' : 'text-yellow-400'}>
                            {(d.confidence * 100).toFixed(0)}%
                          </span>
                        </span>
                      </div>

                      {/* Strategy Weights Bar */}
                      <div className="space-y-1 mb-3">
                        {Object.entries(d.strategy_weights || {})
                          .sort(([,a]: any, [,b]: any) => b - a)
                          .map(([name, weight]: [string, any]) => (
                            <div key={name} className="flex items-center gap-2 text-sm">
                              <span className="w-40 text-gray-400 truncate">{name}</span>
                              <div className="flex-1 bg-gray-800 rounded-full h-3">
                                <div
                                  className={`h-3 rounded-full ${
                                    d.selected_strategies?.includes(name) ? 'bg-blue-500' : 'bg-gray-600'
                                  }`}
                                  style={{ width: `${Math.min(weight * 100, 100)}%` }}
                                />
                              </div>
                              <span className="w-12 text-right font-mono text-xs">
                                {(weight * 100).toFixed(0)}%
                              </span>
                            </div>
                          ))}
                      </div>

                      {/* Reasoning */}
                      <details className="text-xs text-gray-500">
                        <summary className="cursor-pointer hover:text-gray-300">
                          Reasoning ({d.reasoning?.length || 0} factors)
                        </summary>
                        <ul className="mt-2 space-y-0.5 pl-4 list-disc">
                          {d.reasoning?.map((r: string, i: number) => (
                            <li key={i}>{r}</li>
                          ))}
                        </ul>
                      </details>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-center text-gray-500 py-6">
                  No meta-strategy decisions yet. Run a trading cycle to generate decisions.
                </p>
              )}
            </div>
          </div>
        )}

        {activeTab === 'strategies' && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {strategies.map((strat: any) => (
              <div key={strat.name} className="card">
                <h3 className="font-medium text-lg mb-3">{strat.name}</h3>
                <p className="text-sm text-gray-400 mb-3">Type: {strat.type}</p>
                <div className="text-sm space-y-1">
                  {Object.entries(strat.parameters || {}).map(([key, val]) => (
                    <div key={key} className="flex justify-between">
                      <span className="text-gray-400">{key}</span>
                      <span className="font-mono">{String(val)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'logs' && (
          <div className="card">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-medium">System Logs</h3>
              <button onClick={fetchLogs} className="btn-primary text-sm">Refresh</button>
            </div>
            <div className="max-h-[600px] overflow-y-auto text-xs font-mono space-y-1">
              {logs.map((log: any) => (
                <div key={log.id} className={`py-1 px-2 rounded ${
                  log.level === 'ERROR' ? 'bg-red-900/20 text-red-400'
                    : log.level === 'WARNING' ? 'bg-yellow-900/20 text-yellow-400'
                    : 'text-gray-400'
                }`}>
                  <span className="text-gray-600">{formatDate(log.created_at)}</span>
                  {' '}
                  <span className={`font-bold ${
                    log.level === 'ERROR' ? 'text-red-400'
                      : log.level === 'WARNING' ? 'text-yellow-400'
                      : 'text-blue-400'
                  }`}>[{log.level}]</span>
                  {' '}
                  <span className="text-gray-500">[{log.module}]</span>
                  {' '}
                  {log.message}
                </div>
              ))}
              {logs.length === 0 && (
                <p className="text-center text-gray-500 py-8">No logs available</p>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

// ── Helpers ──────────────────────────────────────────────────────────────

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

// ── Root Page ───────────────────────────────────────────────────────────

export default function Page() {
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    setAuthenticated(!!getToken());
  }, []);

  if (!authenticated) {
    return <LoginScreen onLogin={() => setAuthenticated(true)} />;
  }

  return <Dashboard />;
}
