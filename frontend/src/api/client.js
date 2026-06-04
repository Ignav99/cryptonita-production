import axios from 'axios';

// Auto-detect API URL based on environment
const getApiUrl = () => {
  // If VITE_API_URL is set, use it
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }

  // If in production (not localhost), use same origin
  if (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    return `${window.location.protocol}//${window.location.host}/api`;
  }

  // Default to localhost for development
  return 'http://localhost:8000/api';
};

const API_URL = getApiUrl();

// Create axios instance
const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle auth errors
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// Auth API
export const auth = {
  login: async (username, password) => {
    const response = await apiClient.post('/auth/login', {
      username,
      password,
    });
    return response.data;
  },

  logout: () => {
    localStorage.removeItem('token');
    window.location.href = '/login';
  },

  isAuthenticated: () => {
    return !!localStorage.getItem('token');
  },
};

// Dashboard API
export const dashboard = {
  getStats: async () => {
    const response = await apiClient.get('/dashboard/stats');
    return response.data;
  },

  getPositions: async () => {
    const response = await apiClient.get('/dashboard/positions');
    return response.data;
  },

  getClosedPositions: async (limit = 50) => {
    const response = await apiClient.get(`/dashboard/closed-positions?limit=${limit}`);
    return response.data;
  },

  getSignals: async (limit = 50) => {
    const response = await apiClient.get(`/dashboard/signals?limit=${limit}`);
    return response.data;
  },

  getTrades: async (limit = 50) => {
    const response = await apiClient.get(`/dashboard/trades?limit=${limit}`);
    return response.data;
  },

  getBotStatus: async () => {
    const response = await apiClient.get('/dashboard/bot-status');
    return response.data;
  },

  getPerformance: async (days = 30) => {
    const response = await apiClient.get(`/dashboard/performance?days=${days}`);
    return response.data;
  },

  getSignalAnalysis: async () => {
    const response = await apiClient.get('/dashboard/signal-analysis');
    return response.data;
  },

  getSignalsSummary: async () => {
    const response = await apiClient.get('/dashboard/signals/summary');
    return response.data;
  },

  getCoinSummaries: async () => {
    const response = await apiClient.get('/dashboard/signals/coins');
    return response.data;
  },

  getSignalTrends: async (days = 14, tickers = null) => {
    let url = `/dashboard/signals/trends?days=${days}`;
    if (tickers) url += `&tickers=${tickers}`;
    const response = await apiClient.get(url);
    return response.data;
  },

  getThresholdProximity: async () => {
    const response = await apiClient.get('/dashboard/signals/thresholds');
    return response.data;
  },

  getReviewReports: async (limit = 10) => {
    const response = await apiClient.get(`/dashboard/review-reports?limit=${limit}`);
    return response.data;
  },

  getPortfolioValue: async () => {
    const response = await apiClient.get('/dashboard/portfolio-value');
    return response.data;
  },

  backfillPerformance: async () => {
    const response = await apiClient.post('/dashboard/backfill-performance');
    return response.data;
  },
};

// Controls API
export const controls = {
  startBot: async (mode = 'auto') => {
    const response = await apiClient.post('/controls/start', { mode });
    return response.data;
  },

  stopBot: async (reason = 'Manual stop') => {
    const response = await apiClient.post('/controls/stop', { reason });
    return response.data;
  },

  restartBot: async (mode = 'auto') => {
    const response = await apiClient.post('/controls/restart', { mode });
    return response.data;
  },

  pauseBot: async () => {
    const response = await apiClient.post('/controls/pause');
    return response.data;
  },

  getConfig: async () => {
    const response = await apiClient.get('/controls/config');
    return response.data;
  },

  getProcessStatus: async () => {
    const response = await apiClient.get('/controls/process-status');
    return response.data;
  },

  getTrainingStatus: async () => {
    const response = await apiClient.get('/controls/training-status');
    return response.data;
  },

  triggerTraining: async () => {
    const response = await apiClient.post('/controls/trigger-training');
    return response.data;
  },

  resetDatabase: async () => {
    const response = await apiClient.post('/controls/reset-database');
    return response.data;
  },

  softReset: async () => {
    const response = await apiClient.post('/controls/soft-reset');
    return response.data;
  },
};

export default apiClient;
