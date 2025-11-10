import React, { useState, useEffect } from 'react';
import { RefreshCw } from 'lucide-react';
import { dashboard } from '../api/client';
import useWebSocket from '../hooks/useWebSocket';
import Stats from './Stats';
import BotControls from './BotControls';
import Positions from './Positions';
import Signals from './Signals';
import Trades from './Trades';

const Dashboard = () => {
  const [stats, setStats] = useState(null);
  const [positions, setPositions] = useState([]);
  const [signals, setSignals] = useState([]);
  const [trades, setTrades] = useState([]);
  const [botStatus, setBotStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(new Date());

  // WebSocket for real-time updates
  const { data: wsData, isConnected } = useWebSocket('/dashboard');

  // Fetch all data
  const fetchData = async () => {
    try {
      const [statsData, positionsData, signalsData, tradesData, statusData] =
        await Promise.all([
          dashboard.getStats(),
          dashboard.getPositions(),
          dashboard.getSignals(50),
          dashboard.getTrades(50),
          dashboard.getBotStatus(),
        ]);

      setStats(statsData);
      setPositions(positionsData);
      setSignals(signalsData);
      setTrades(tradesData);
      setBotStatus(statusData);
      setLastUpdate(new Date());
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error);
    } finally {
      setLoading(false);
    }
  };

  // Initial load
  useEffect(() => {
    fetchData();

    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchData, 30000);

    return () => clearInterval(interval);
  }, []);

  // Handle WebSocket updates
  useEffect(() => {
    if (wsData) {
      console.log('📡 WebSocket update:', wsData);

      // Update relevant data based on message type
      if (wsData.type === 'stats') {
        setStats(wsData.data);
      } else if (wsData.type === 'position_update') {
        fetchData(); // Refresh all data on position change
      } else if (wsData.type === 'new_signal') {
        setSignals((prev) => [wsData.data, ...prev]);
      } else if (wsData.type === 'new_trade') {
        setTrades((prev) => [wsData.data, ...prev]);
      }
    }
  }, [wsData]);

  const handleRefresh = () => {
    setLoading(true);
    fetchData();
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <div className="spinner mx-auto mb-4"></div>
          <p className="text-gray-600">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">
                Cryptonita Trading Bot
              </h1>
              <p className="text-sm text-gray-600 mt-1">
                ML-Powered Cryptocurrency Trading Dashboard
              </p>
            </div>

            <div className="flex items-center gap-4">
              {/* WebSocket Status */}
              <div className="flex items-center gap-2">
                <span
                  className={`w-2 h-2 rounded-full ${
                    isConnected ? 'bg-green-500 animate-pulse' : 'bg-red-500'
                  }`}
                />
                <span className="text-xs text-gray-600">
                  {isConnected ? 'Live' : 'Offline'}
                </span>
              </div>

              {/* Refresh Button */}
              <button
                onClick={handleRefresh}
                className="btn-secondary flex items-center gap-2 text-sm"
                disabled={loading}
              >
                <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </button>

              {/* Last Update */}
              <span className="text-xs text-gray-500">
                Updated: {lastUpdate.toLocaleTimeString()}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="space-y-6">
          {/* Stats Cards */}
          <Stats stats={stats} />

          {/* Bot Controls + Positions */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Bot Controls */}
            <div className="lg:col-span-1">
              <BotControls botStatus={botStatus} onStatusChange={fetchData} />
            </div>

            {/* Positions */}
            <div className="lg:col-span-2">
              <Positions positions={positions} />
            </div>
          </div>

          {/* Signals + Trades */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Recent Signals */}
            <Signals signals={signals} limit={10} />

            {/* Trade History */}
            <Trades trades={trades} limit={20} />
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between text-sm text-gray-600">
            <div>
              <span className="font-semibold">Cryptonita V3</span>
              <span className="mx-2">•</span>
              <span>XGBoost Model</span>
              <span className="mx-2">•</span>
              <span>48 Features</span>
              <span className="mx-2">•</span>
              <span>Dynamic TP/SL</span>
            </div>

            <div>
              <span>Mode: {botStatus?.status || 'Unknown'}</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Dashboard;
