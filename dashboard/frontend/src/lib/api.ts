const API_BASE = '/api';

let authToken: string | null = null;

export function setToken(token: string) {
  authToken = token;
  if (typeof window !== 'undefined') {
    localStorage.setItem('fx_token', token);
  }
}

export function getToken(): string | null {
  if (authToken) return authToken;
  if (typeof window !== 'undefined') {
    authToken = localStorage.getItem('fx_token');
  }
  return authToken;
}

export function clearToken() {
  authToken = null;
  if (typeof window !== 'undefined') {
    localStorage.removeItem('fx_token');
  }
}

async function fetchAPI(path: string, options: RequestInit = {}) {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> || {}),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    throw new Error('Unauthorized');
  }
  if (!res.ok) {
    throw new Error(`API error: ${res.status}`);
  }
  return res.json();
}

export async function login(username: string, password: string) {
  const formData = new URLSearchParams();
  formData.append('username', username);
  formData.append('password', password);

  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData.toString(),
  });

  if (!res.ok) throw new Error('Login failed');
  const data = await res.json();
  setToken(data.access_token);
  return data;
}

export const api = {
  getStatus: () => fetchAPI('/status'),
  getTrades: (params?: string) => fetchAPI(`/trades${params ? `?${params}` : ''}`),
  getPositions: () => fetchAPI('/positions'),
  getPerformance: () => fetchAPI('/performance'),
  getBalance: () => fetchAPI('/balance'),
  getLiveAccount: () => fetchAPI('/account/live'),
  getStrategies: () => fetchAPI('/strategies'),
  getLogs: (limit = 100) => fetchAPI(`/logs?limit=${limit}`),
  controlBot: (action: string) =>
    fetchAPI('/control', { method: 'POST', body: JSON.stringify({ action }) }),
  updatePairs: (pairs: string[]) =>
    fetchAPI('/pairs', { method: 'POST', body: JSON.stringify({ pairs }) }),

  // News filter config
  getNewsConfig: () => fetchAPI('/news/config'),
  setNewsManualSource: (enabled: boolean) =>
    fetchAPI('/news/manual-source', {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    }),

  // Meta-Strategy endpoints
  getMetaDecisions: () => fetchAPI('/meta/decisions'),
  getMetaDecision: (symbol: string) => fetchAPI(`/meta/decisions/${symbol}`),
  getStrategyRankings: (days = 30) => fetchAPI(`/meta/rankings?days=${days}`),
  getStrategyPerformance: (strategy: string, days = 60) =>
    fetchAPI(`/meta/performance/${strategy}?days=${days}`),
  getSession: () => fetchAPI('/meta/session'),
  getRegimeHistory: (limit = 100) => fetchAPI(`/meta/regimes?limit=${limit}`),
};
