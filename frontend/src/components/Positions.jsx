import React from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { formatDistance } from 'date-fns';

const Positions = ({ positions, limit = 20 }) => {
  // Apply limit to positions
  const displayPositions = positions?.slice(0, limit) || [];
  const hasMore = positions && positions.length > limit;

  if (!positions || positions.length === 0) {
    return (
      <div className="card">
        <h2 className="text-xl font-bold text-gray-800 mb-4">Open Positions</h2>
        <div className="text-center py-8 text-gray-500">
          <p>No open positions</p>
          <p className="text-sm mt-2">Positions will appear here when bot executes trades</p>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-gray-800">Open Positions</h2>
        <div className="flex items-center gap-2">
          <span className="badge badge-info">{positions.length} active</span>
          {hasMore && (
            <span className="text-xs text-gray-500">Showing {limit} of {positions.length}</span>
          )}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="table">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Entry</th>
              <th>Current</th>
              <th>Size</th>
              <th>P&L</th>
              <th>TP/SL</th>
              <th>Duration</th>
            </tr>
          </thead>
          <tbody>
            {displayPositions.map((position, index) => {
              const pnl = position.pnl || 0;
              const pnlPct = position.pnl_percentage || 0;
              const isProfit = pnl >= 0;

              return (
                <tr key={index}>
                  <td>
                    <span className="font-semibold text-gray-900">{position.ticker}</span>
                  </td>

                  <td>
                    <span className="font-mono text-sm">${position.entry_price?.toFixed(4)}</span>
                  </td>

                  <td>
                    <span className="font-mono text-sm">
                      ${position.current_price?.toFixed(4)}
                    </span>
                  </td>

                  <td>
                    <div className="text-sm">
                      <div className="font-mono">{position.quantity?.toFixed(4)}</div>
                      <div className="text-gray-500">${position.total_value?.toFixed(2)}</div>
                    </div>
                  </td>

                  <td>
                    <div className={`flex items-center gap-1 ${isProfit ? 'text-green-600' : 'text-red-600'}`}>
                      {isProfit ? (
                        <TrendingUp className="w-4 h-4" />
                      ) : (
                        <TrendingDown className="w-4 h-4" />
                      )}
                      <div className="text-sm">
                        <div className="font-semibold">
                          {isProfit ? '+' : ''}${pnl.toFixed(2)}
                        </div>
                        <div className="text-xs">
                          ({isProfit ? '+' : ''}{pnlPct.toFixed(2)}%)
                        </div>
                      </div>
                    </div>
                  </td>

                  <td>
                    <div className="text-xs text-gray-600">
                      <div>
                        TP: ${position.take_profit?.toFixed(4)}
                      </div>
                      <div>
                        SL: ${position.stop_loss?.toFixed(4)}
                      </div>
                    </div>
                  </td>

                  <td className="text-sm text-gray-600">
                    {position.entry_time &&
                      formatDistance(new Date(position.entry_time), new Date(), {
                        addSuffix: true,
                      })}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default Positions;
