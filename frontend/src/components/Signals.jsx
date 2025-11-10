import React from 'react';
import { TrendingUp, Clock } from 'lucide-react';
import { formatDistance } from 'date-fns';

const Signals = ({ signals, limit = 10 }) => {
  const displaySignals = signals?.slice(0, limit) || [];
  const buySignals = displaySignals.filter((s) => s.signal_type === 'BUY');

  if (!signals || signals.length === 0) {
    return (
      <div className="card">
        <h2 className="text-xl font-bold text-gray-800 mb-4">Recent Signals</h2>
        <div className="text-center py-8 text-gray-500">
          <p>No signals yet</p>
          <p className="text-sm mt-2">Signals will appear when bot scans the market</p>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-gray-800">Recent Signals</h2>
        <div className="flex items-center gap-2">
          <span className="badge badge-success">{buySignals.length} BUY</span>
          <span className="badge badge-info">{displaySignals.length} total</span>
        </div>
      </div>

      <div className="space-y-2 max-h-96 overflow-y-auto">
        {displaySignals.map((signal, index) => {
          const isBuy = signal.signal_type === 'BUY';
          const probability = (signal.probability * 100).toFixed(1);

          return (
            <div
              key={index}
              className={`p-3 rounded-lg border-l-4 ${
                isBuy
                  ? 'bg-green-50 border-green-500'
                  : 'bg-gray-50 border-gray-300'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  {isBuy && <TrendingUp className="w-5 h-5 text-green-600" />}

                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-gray-900">{signal.ticker}</span>
                      <span
                        className={`badge ${
                          isBuy ? 'badge-success' : 'badge-warning'
                        }`}
                      >
                        {signal.signal_type}
                      </span>
                    </div>

                    <div className="text-xs text-gray-600 mt-1 flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {signal.timestamp &&
                        formatDistance(new Date(signal.timestamp), new Date(), {
                          addSuffix: true,
                        })}
                    </div>
                  </div>
                </div>

                <div className="text-right">
                  <div className="text-sm font-semibold text-gray-900">
                    {probability}%
                  </div>
                  <div className="text-xs text-gray-600">confidence</div>
                </div>
              </div>

              {/* Features Preview (optional) */}
              {isBuy && signal.features && (
                <div className="mt-2 pt-2 border-t border-green-200 grid grid-cols-3 gap-2 text-xs">
                  <div>
                    <span className="text-gray-600">Momentum 3d:</span>
                    <span className="ml-1 font-mono text-gray-900">
                      {(signal.features.momentum_3d * 100).toFixed(1)}%
                    </span>
                  </div>

                  <div>
                    <span className="text-gray-600">ATR:</span>
                    <span className="ml-1 font-mono text-gray-900">
                      {(signal.features.atr_pct * 100).toFixed(1)}%
                    </span>
                  </div>

                  <div>
                    <span className="text-gray-600">Volume:</span>
                    <span className="ml-1 font-mono text-gray-900">
                      {signal.features.volume_ratio_20?.toFixed(2)}x
                    </span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default Signals;
