import React, { useState, useEffect } from 'react';
import { Brain, Play, CheckCircle, XCircle, Clock, AlertTriangle, TrendingUp, Award, RefreshCw } from 'lucide-react';
import { controls } from '../api/client';

const Training = () => {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [triggering, setTriggering] = useState(false);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);

  const fetchStatus = async () => {
    try {
      const data = await controls.getTrainingStatus();
      setStatus(data);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch training status:', err);
      setError('Failed to load training status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleTriggerTraining = async () => {
    setTriggering(true);
    setError(null);
    setSuccessMsg(null);

    try {
      const result = await controls.triggerTraining();
      if (result.success) {
        setSuccessMsg(result.message);
        setTimeout(fetchStatus, 3000);
      } else {
        setError(result.message);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to trigger training');
    } finally {
      setTriggering(false);
    }
  };

  const getStatusIcon = (runStatus) => {
    switch (runStatus) {
      case 'promoted':
        return <Award className="w-4 h-4 text-green-500" />;
      case 'completed':
        return <CheckCircle className="w-4 h-4 text-blue-500" />;
      case 'running':
        return <RefreshCw className="w-4 h-4 text-yellow-500 animate-spin" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-red-500" />;
      default:
        return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  const getStatusBadge = (runStatus) => {
    const styles = {
      promoted: 'badge-success',
      completed: 'badge-info',
      running: 'badge-warning',
      failed: 'badge-danger',
    };
    return styles[runStatus] || 'badge-info';
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    const d = new Date(dateStr);
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatMetric = (value, type = 'number') => {
    if (value === undefined || value === null) return '-';
    if (type === 'percent') return `${(value * 100).toFixed(1)}%`;
    if (type === 'decimal') return value.toFixed(2);
    return value.toFixed(4);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="spinner mr-3"></div>
        <span className="text-gray-600">Loading training data...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Active Model */}
        <div className="card">
          <div className="flex items-center gap-2 mb-2">
            <Brain className="w-5 h-5 text-purple-600" />
            <span className="text-sm font-medium text-gray-600">Active Model</span>
          </div>
          <div className="text-2xl font-bold text-gray-900">
            {status?.has_active_model ? `v${status.active_model_version}` : 'None'}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {status?.has_active_model ? 'Stored in PostgreSQL' : 'No model in DB'}
          </div>
        </div>

        {/* Auto-Train Status */}
        <div className="card">
          <div className="flex items-center gap-2 mb-2">
            <RefreshCw className="w-5 h-5 text-blue-600" />
            <span className="text-sm font-medium text-gray-600">Auto-Train</span>
          </div>
          <div className="text-2xl font-bold text-gray-900">
            {status?.auto_train_enabled ? (
              <span className="text-green-600">Enabled</span>
            ) : (
              <span className="text-gray-400">Disabled</span>
            )}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            Every {status?.auto_train_interval_days || 7} days
          </div>
        </div>

        {/* Training Status */}
        <div className="card">
          <div className="flex items-center gap-2 mb-2">
            <Clock className="w-5 h-5 text-yellow-600" />
            <span className="text-sm font-medium text-gray-600">Current Status</span>
          </div>
          <div className="text-2xl font-bold">
            {status?.is_training ? (
              <span className="text-yellow-600 flex items-center gap-2">
                <RefreshCw className="w-5 h-5 animate-spin" />
                Training...
              </span>
            ) : (
              <span className="text-gray-600">Idle</span>
            )}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {status?.is_training ? 'Model being trained' : 'Ready for next cycle'}
          </div>
        </div>

        {/* Total Runs */}
        <div className="card">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-5 h-5 text-green-600" />
            <span className="text-sm font-medium text-gray-600">Training Runs</span>
          </div>
          <div className="text-2xl font-bold text-gray-900">
            {status?.training_history?.length || 0}
          </div>
          <div className="text-xs text-gray-500 mt-1">
            {status?.training_history?.filter((h) => h.promoted).length || 0} promoted
          </div>
        </div>
      </div>

      {/* Manual Training + Messages */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
            <Play className="w-5 h-5 text-blue-600" />
            Manual Training
          </h2>
          <button
            onClick={handleTriggerTraining}
            disabled={triggering || status?.is_training}
            className="btn-primary flex items-center gap-2"
          >
            {triggering ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            {triggering ? 'Starting...' : 'Trigger Training'}
          </button>
        </div>

        <p className="text-sm text-gray-600 mb-3">
          Manually start a training cycle. The new model will only be promoted if it
          outperforms the current active model (Sharpe, Win Rate, Max Drawdown checks).
        </p>

        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            {error}
          </div>
        )}

        {successMsg && (
          <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm flex items-center gap-2">
            <CheckCircle className="w-4 h-4" />
            {successMsg}
          </div>
        )}
      </div>

      {/* Training History */}
      <div className="card">
        <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2 mb-4">
          <Clock className="w-5 h-5 text-gray-600" />
          Training History
        </h2>

        {!status?.training_history || status.training_history.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <Brain className="w-12 h-12 mx-auto mb-3 text-gray-300" />
            <p className="font-medium">No training runs yet</p>
            <p className="text-sm mt-1">
              The first training will run automatically 1 hour after bot start,
              or you can trigger one manually above.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th className="text-left py-3 px-4">Status</th>
                  <th className="text-left py-3 px-4">Version</th>
                  <th className="text-left py-3 px-4">Mode</th>
                  <th className="text-left py-3 px-4">Started</th>
                  <th className="text-right py-3 px-4">AUC</th>
                  <th className="text-right py-3 px-4">Sharpe</th>
                  <th className="text-right py-3 px-4">Win Rate</th>
                  <th className="text-right py-3 px-4">ROI</th>
                  <th className="text-center py-3 px-4">Promoted</th>
                </tr>
              </thead>
              <tbody>
                {status.training_history.map((run) => (
                  <tr key={run.id} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="py-3 px-4">
                      <div className="flex items-center gap-2">
                        {getStatusIcon(run.status)}
                        <span className={getStatusBadge(run.status)}>
                          {run.status}
                        </span>
                      </div>
                    </td>
                    <td className="py-3 px-4 font-mono font-medium">v{run.version}</td>
                    <td className="py-3 px-4">
                      <span className="text-xs font-medium px-2 py-1 rounded bg-gray-100 text-gray-700">
                        {run.mode}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-sm text-gray-600">
                      {formatDate(run.started_at)}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-sm">
                      {formatMetric(run.metrics?.auc_roc)}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-sm">
                      {formatMetric(run.metrics?.sharpe, 'decimal')}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-sm">
                      {formatMetric(run.metrics?.win_rate, 'percent')}
                    </td>
                    <td className="py-3 px-4 text-right font-mono text-sm">
                      <span
                        className={
                          run.metrics?.roi > 0
                            ? 'text-green-600'
                            : run.metrics?.roi < 0
                            ? 'text-red-600'
                            : ''
                        }
                      >
                        {formatMetric(run.metrics?.roi, 'percent')}
                      </span>
                    </td>
                    <td className="py-3 px-4 text-center">
                      {run.promoted ? (
                        <Award className="w-5 h-5 text-green-500 mx-auto" />
                      ) : (
                        <span className="text-gray-300">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Latest Run Details (if there is a recent promoted or failed run) */}
      {status?.training_history?.[0]?.comparison &&
        Object.keys(status.training_history[0].comparison).length > 0 && (
          <div className="card">
            <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2 mb-4">
              <TrendingUp className="w-5 h-5 text-blue-600" />
              Latest Comparison (v{status.training_history[0].version})
            </h2>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {(() => {
                const cmp = status.training_history[0].comparison;
                return (
                  <>
                    <div className="bg-gray-50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">New Sharpe</div>
                      <div className="font-mono font-bold">
                        {cmp.new_sharpe?.toFixed(2) || '-'}
                      </div>
                    </div>
                    <div className="bg-gray-50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Current Sharpe</div>
                      <div className="font-mono font-bold">
                        {cmp.current_sharpe?.toFixed(2) || '-'}
                      </div>
                    </div>
                    <div className="bg-gray-50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">New Win Rate</div>
                      <div className="font-mono font-bold">
                        {cmp.new_win_rate ? `${(cmp.new_win_rate * 100).toFixed(1)}%` : '-'}
                      </div>
                    </div>
                    <div className="bg-gray-50 rounded-lg p-3">
                      <div className="text-xs text-gray-500 mb-1">Max Drawdown</div>
                      <div className="font-mono font-bold">
                        {cmp.new_max_drawdown
                          ? `${(cmp.new_max_drawdown * 100).toFixed(1)}%`
                          : '-'}
                      </div>
                    </div>
                  </>
                );
              })()}
            </div>

            {status.training_history[0].comparison.promotion_reason && (
              <div className="mt-3 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm">
                {status.training_history[0].comparison.promotion_reason}
              </div>
            )}

            {status.training_history[0].comparison.rejection_reason && (
              <div className="mt-3 p-3 bg-yellow-50 border border-yellow-200 rounded-lg text-yellow-700 text-sm">
                {status.training_history[0].comparison.rejection_reason}
              </div>
            )}

            {status.training_history[0].error_message && (
              <div className="mt-3 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                Error: {status.training_history[0].error_message}
              </div>
            )}
          </div>
        )}
    </div>
  );
};

export default Training;
