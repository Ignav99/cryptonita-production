import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Target, Clock, BarChart3, AlertCircle } from 'lucide-react';
import { dashboard } from '../api/client';

const Analysis = () => {
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchAnalysis = async () => {
      try {
        setLoading(true);
        const data = await dashboard.getSignalAnalysis();
        setAnalysis(data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch analysis:', err);
        setError('Failed to load signal analysis');
      } finally {
        setLoading(false);
      }
    };

    fetchAnalysis();
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="card">
          <div className="text-center py-12">
            <div className="spinner mx-auto mb-4"></div>
            <p className="text-gray-600">Loading signal analysis...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card">
        <div className="text-center py-8 text-red-500">
          <AlertCircle className="w-12 h-12 mx-auto mb-4" />
          <p>{error}</p>
        </div>
      </div>
    );
  }

  if (!analysis || analysis.total_signals === 0) {
    return (
      <div className="card">
        <h2 className="text-xl font-bold text-gray-800 mb-4">Signal Performance Analysis</h2>
        <div className="text-center py-8 text-gray-500">
          <BarChart3 className="w-12 h-12 mx-auto mb-4 text-gray-400" />
          <p>No signals to analyze yet</p>
          <p className="text-sm mt-2">Analysis will appear when the bot generates BUY signals</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Mature Hit Rate */}
        <div className="card bg-gradient-to-br from-green-50 to-green-100 border-green-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-green-700 font-medium">Mature Hit Rate</p>
              <p className="text-3xl font-bold text-green-800">{analysis.mature_hit_rate}%</p>
              <p className="text-xs text-green-600 mt-1">{analysis.mature_signals} signals with 20+ days</p>
            </div>
            <Target className="w-10 h-10 text-green-500" />
          </div>
        </div>

        {/* Mature Avg Return */}
        <div className="card bg-gradient-to-br from-blue-50 to-blue-100 border-blue-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-blue-700 font-medium">Mature Avg Return</p>
              <p className="text-3xl font-bold text-blue-800">+{analysis.mature_avg_return}%</p>
              <p className="text-xs text-blue-600 mt-1">Max return achieved</p>
            </div>
            <TrendingUp className="w-10 h-10 text-blue-500" />
          </div>
        </div>

        {/* Total Signals */}
        <div className="card bg-gradient-to-br from-purple-50 to-purple-100 border-purple-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-purple-700 font-medium">Total Signals</p>
              <p className="text-3xl font-bold text-purple-800">{analysis.total_signals}</p>
              <p className="text-xs text-purple-600 mt-1">BUY signals analyzed</p>
            </div>
            <BarChart3 className="w-10 h-10 text-purple-500" />
          </div>
        </div>

        {/* Overall Avg Return */}
        <div className="card bg-gradient-to-br from-orange-50 to-orange-100 border-orange-200">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-orange-700 font-medium">Overall Avg Return</p>
              <p className="text-3xl font-bold text-orange-800">+{analysis.avg_return}%</p>
              <p className="text-xs text-orange-600 mt-1">All signals (incl. recent)</p>
            </div>
            <Clock className="w-10 h-10 text-orange-500" />
          </div>
        </div>
      </div>

      {/* Model Status Indicator */}
      <div className={`card ${
        analysis.mature_hit_rate >= 60
          ? 'bg-green-50 border-green-300'
          : analysis.mature_hit_rate >= 40
            ? 'bg-yellow-50 border-yellow-300'
            : 'bg-red-50 border-red-300'
      }`}>
        <div className="flex items-center gap-4">
          <div className={`w-4 h-4 rounded-full ${
            analysis.mature_hit_rate >= 60
              ? 'bg-green-500'
              : analysis.mature_hit_rate >= 40
                ? 'bg-yellow-500'
                : 'bg-red-500'
          }`} />
          <div>
            <p className={`font-bold ${
              analysis.mature_hit_rate >= 60
                ? 'text-green-800'
                : analysis.mature_hit_rate >= 40
                  ? 'text-yellow-800'
                  : 'text-red-800'
            }`}>
              {analysis.mature_hit_rate >= 60
                ? 'MODEL PERFORMING WELL'
                : analysis.mature_hit_rate >= 40
                  ? 'MODEL PERFORMING MODERATELY'
                  : 'MODEL NEEDS REVIEW'}
            </p>
            <p className={`text-sm ${
              analysis.mature_hit_rate >= 60
                ? 'text-green-700'
                : analysis.mature_hit_rate >= 40
                  ? 'text-yellow-700'
                  : 'text-red-700'
            }`}>
              {analysis.mature_hit_rate >= 60
                ? 'Mature signals are correctly predicting price pumps (+20% target)'
                : analysis.mature_hit_rate >= 40
                  ? 'Some signals hit target, performance is acceptable but not optimal'
                  : 'Signals are not correlating well with +20% pumps'}
            </p>
          </div>
        </div>
      </div>

      {/* Performance by Probability */}
      {analysis.by_probability && analysis.by_probability.length > 0 && (
        <div className="card">
          <h3 className="text-lg font-bold text-gray-800 mb-4">Performance by Probability Range</h3>
          <div className="overflow-x-auto">
            <table className="table">
              <thead>
                <tr>
                  <th>Probability</th>
                  <th>Signals</th>
                  <th>Hit Rate (+20%)</th>
                  <th>Avg Return</th>
                </tr>
              </thead>
              <tbody>
                {analysis.by_probability.map((row, index) => (
                  <tr key={index}>
                    <td className="font-medium">{row.range}</td>
                    <td>{row.count}</td>
                    <td>
                      <span className={`badge ${
                        row.hit_rate >= 60 ? 'badge-success' :
                        row.hit_rate >= 40 ? 'badge-warning' : 'badge-error'
                      }`}>
                        {row.hit_rate}%
                      </span>
                    </td>
                    <td className={row.avg_return >= 0 ? 'text-green-600' : 'text-red-600'}>
                      {row.avg_return >= 0 ? '+' : ''}{row.avg_return}%
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Best & Worst Signals */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Best Signals */}
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-5 h-5 text-green-600" />
            <h3 className="text-lg font-bold text-gray-800">Top 5 Best Signals</h3>
          </div>
          <div className="space-y-2">
            {analysis.best_signals && analysis.best_signals.map((signal, index) => (
              <div key={index} className="p-3 bg-green-50 rounded-lg border-l-4 border-green-500">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-semibold text-gray-900">{signal.ticker}</span>
                    <span className="text-xs text-gray-500 ml-2">{signal.signal_date}</span>
                  </div>
                  <div className="text-right">
                    <span className="text-lg font-bold text-green-600">+{signal.max_return_pct}%</span>
                    <div className="text-xs text-gray-500">prob: {(signal.probability * 100).toFixed(0)}%</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Worst Signals */}
        <div className="card">
          <div className="flex items-center gap-2 mb-4">
            <TrendingDown className="w-5 h-5 text-red-600" />
            <h3 className="text-lg font-bold text-gray-800">Top 5 Worst Signals</h3>
          </div>
          <div className="space-y-2">
            {analysis.worst_signals && analysis.worst_signals.map((signal, index) => (
              <div key={index} className="p-3 bg-red-50 rounded-lg border-l-4 border-red-400">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="font-semibold text-gray-900">{signal.ticker}</span>
                    <span className="text-xs text-gray-500 ml-2">{signal.signal_date}</span>
                  </div>
                  <div className="text-right">
                    <span className={`text-lg font-bold ${signal.max_return_pct >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                      {signal.max_return_pct >= 0 ? '+' : ''}{signal.max_return_pct}%
                    </span>
                    <div className="text-xs text-gray-500">prob: {(signal.probability * 100).toFixed(0)}%</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Recent Signals */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Clock className="w-5 h-5 text-blue-600" />
          <h3 className="text-lg font-bold text-gray-800">Recent Signals Performance</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Ticker</th>
                <th>Probability</th>
                <th>Entry Price</th>
                <th>Max Price</th>
                <th>Max Return</th>
                <th>Days</th>
                <th>Target</th>
              </tr>
            </thead>
            <tbody>
              {analysis.recent_signals && analysis.recent_signals.map((signal, index) => (
                <tr key={index}>
                  <td className="text-sm">{signal.signal_date}</td>
                  <td className="font-medium">{signal.ticker}</td>
                  <td>{(signal.probability * 100).toFixed(0)}%</td>
                  <td>${signal.entry_price.toFixed(4)}</td>
                  <td>${signal.max_price.toFixed(4)}</td>
                  <td className={signal.max_return_pct >= 0 ? 'text-green-600 font-medium' : 'text-red-600 font-medium'}>
                    {signal.max_return_pct >= 0 ? '+' : ''}{signal.max_return_pct}%
                  </td>
                  <td>
                    <span className={`text-xs ${signal.days_available >= 20 ? 'text-green-600' : 'text-orange-500'}`}>
                      {signal.days_available}d
                    </span>
                  </td>
                  <td>
                    {signal.hit_20pct ? (
                      <span className="badge badge-success">HIT</span>
                    ) : signal.days_available < 20 ? (
                      <span className="badge badge-warning">Pending</span>
                    ) : (
                      <span className="badge badge-error">Miss</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-gray-500 mt-3">
          Note: Signals with less than 20 days are marked as "Pending" - they haven't had enough time to reach the +20% target.
        </p>
      </div>
    </div>
  );
};

export default Analysis;
