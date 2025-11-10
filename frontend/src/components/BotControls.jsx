import React, { useState, useEffect } from 'react';
import { Play, Square, RotateCw, Pause, Cpu, Activity } from 'lucide-react';
import { controls } from '../api/client';

const BotControls = ({ botStatus, onStatusChange }) => {
  const [loading, setLoading] = useState(false);
  const [processStatus, setProcessStatus] = useState(null);
  const [error, setError] = useState(null);

  const isRunning = botStatus?.status === 'running';
  const isPaused = botStatus?.status === 'idle';

  // Fetch process status
  useEffect(() => {
    const fetchProcessStatus = async () => {
      try {
        const status = await controls.getProcessStatus();
        setProcessStatus(status);
      } catch (err) {
        console.error('Failed to fetch process status:', err);
      }
    };

    fetchProcessStatus();
    const interval = setInterval(fetchProcessStatus, 5000);

    return () => clearInterval(interval);
  }, []);

  const handleStart = async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await controls.startBot('auto');
      if (result.success) {
        onStatusChange?.();
      } else {
        setError(result.message);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to start bot');
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await controls.stopBot('Manual stop from dashboard');
      if (result.success) {
        onStatusChange?.();
      } else {
        setError(result.message);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to stop bot');
    } finally {
      setLoading(false);
    }
  };

  const handleRestart = async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await controls.restartBot('auto');
      if (result.success) {
        onStatusChange?.();
      } else {
        setError(result.message);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to restart bot');
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async () => {
    setLoading(true);
    setError(null);

    try {
      const result = await controls.pauseBot();
      if (result.success) {
        onStatusChange?.();
      } else {
        setError(result.message);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to pause bot');
    } finally {
      setLoading(false);
    }
  };

  const formatUptime = (seconds) => {
    if (!seconds) return '0s';

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
      return `${hours}h ${minutes}m`;
    } else if (minutes > 0) {
      return `${minutes}m ${secs}s`;
    } else {
      return `${secs}s`;
    }
  };

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
          <Activity className="w-6 h-6 text-blue-600" />
          Bot Control
        </h2>

        <div className="flex items-center gap-2">
          <span
            className={`w-3 h-3 rounded-full ${
              isRunning ? 'bg-green-500 animate-pulse' : 'bg-red-500'
            }`}
          />
          <span className="text-sm font-medium text-gray-600">
            {isRunning ? 'Running' : isPaused ? 'Paused' : 'Stopped'}
          </span>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Control Buttons */}
      <div className="grid grid-cols-2 gap-3 mb-6">
        <button
          onClick={handleStart}
          disabled={loading || isRunning}
          className="btn-success flex items-center justify-center gap-2"
        >
          <Play className="w-4 h-4" />
          Start Bot
        </button>

        <button
          onClick={handleStop}
          disabled={loading || !isRunning}
          className="btn-danger flex items-center justify-center gap-2"
        >
          <Square className="w-4 h-4" />
          Stop Bot
        </button>

        <button
          onClick={handlePause}
          disabled={loading || !isRunning}
          className="btn-secondary flex items-center justify-center gap-2"
        >
          <Pause className="w-4 h-4" />
          Pause
        </button>

        <button
          onClick={handleRestart}
          disabled={loading}
          className="btn-primary flex items-center justify-center gap-2"
        >
          <RotateCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          Restart
        </button>
      </div>

      {/* Process Status */}
      {processStatus && processStatus.running && (
        <div className="bg-gray-50 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <Cpu className="w-4 h-4 text-gray-600" />
            <span className="text-sm font-semibold text-gray-700">Process Status</span>
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-gray-600">PID:</span>
              <span className="ml-2 font-mono text-gray-900">{processStatus.pid}</span>
            </div>

            <div>
              <span className="text-gray-600">Uptime:</span>
              <span className="ml-2 font-mono text-gray-900">
                {formatUptime(processStatus.uptime_seconds)}
              </span>
            </div>

            <div>
              <span className="text-gray-600">CPU:</span>
              <span className="ml-2 font-mono text-gray-900">
                {processStatus.cpu_percent.toFixed(1)}%
              </span>
            </div>

            <div>
              <span className="text-gray-600">Memory:</span>
              <span className="ml-2 font-mono text-gray-900">
                {processStatus.memory_mb.toFixed(1)} MB
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Bot Info */}
      {botStatus && (
        <div className="mt-4 pt-4 border-t border-gray-200">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-gray-600">Cycle:</span>
              <span className="ml-2 font-semibold text-gray-900">
                #{botStatus.cycle_number || 0}
              </span>
            </div>

            <div>
              <span className="text-gray-600">Signals:</span>
              <span className="ml-2 font-semibold text-gray-900">
                {botStatus.buy_signals || 0} / {botStatus.total_signals || 0}
              </span>
            </div>
          </div>

          {botStatus.last_error && (
            <div className="mt-3 p-2 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-800">
              Last error: {botStatus.last_error}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default BotControls;
