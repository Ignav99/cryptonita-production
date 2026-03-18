import React from 'react';
import { TrendingUp, TrendingDown, CheckCircle, XCircle, Clock } from 'lucide-react';
import { formatDistance } from 'date-fns';

const ClosedPositions = ({ closedPositions }) => {
  if (!closedPositions || closedPositions.length === 0) {
    return (
      <div className="card">
        <h2 className="text-xl font-bold text-gray-800 mb-4 flex items-center gap-2">
          <CheckCircle className="w-5 h-5 text-green-600" />
          Closed Positions
        </h2>
        <div className="text-center py-8 text-gray-500">
          <XCircle className="w-12 h-12 mx-auto mb-3 text-gray-400" />
          <p>No closed positions yet</p>
          <p className="text-sm mt-2">Positions will appear here when trades are closed</p>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
          <CheckCircle className="w-5 h-5 text-green-600" />
          Closed Positions
        </h2>
        <span className="badge badge-info">{closedPositions.length} closed</span>
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Ticker
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Entry Price
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Exit Price
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                P&L
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                P&L %
              </th>
              <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                Model Conf.
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Closed
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {closedPositions.map((position, index) => {
              const isProfit = position.pnl > 0;
              const pnlColor = isProfit ? 'text-green-600' : 'text-red-600';
              const bgColor = isProfit ? 'bg-green-50' : 'bg-red-50';

              return (
                <tr key={index} className={`hover:${bgColor} transition-colors`}>
                  {/* Ticker */}
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="flex items-center gap-2">
                      {isProfit ? (
                        <TrendingUp className="w-4 h-4 text-green-600" />
                      ) : (
                        <TrendingDown className="w-4 h-4 text-red-600" />
                      )}
                      <span className="font-semibold text-gray-900">{position.ticker}</span>
                    </div>
                  </td>

                  {/* Entry Price */}
                  <td className="px-4 py-3 whitespace-nowrap text-right">
                    <span className="text-sm font-mono text-gray-700">
                      ${position.entry_price?.toFixed(4) || '0.0000'}
                    </span>
                  </td>

                  {/* Exit Price */}
                  <td className="px-4 py-3 whitespace-nowrap text-right">
                    <span className="text-sm font-mono text-gray-700">
                      ${position.exit_price?.toFixed(4) || '0.0000'}
                    </span>
                  </td>

                  {/* P&L (dollars) */}
                  <td className="px-4 py-3 whitespace-nowrap text-right">
                    <span className={`text-sm font-semibold font-mono ${pnlColor}`}>
                      {isProfit ? '+' : ''}${position.pnl?.toFixed(2) || '0.00'}
                    </span>
                  </td>

                  {/* P&L (percentage) */}
                  <td className="px-4 py-3 whitespace-nowrap text-right">
                    <div className="flex items-center justify-end gap-1">
                      {isProfit ? (
                        <TrendingUp className="w-3 h-3 text-green-600" />
                      ) : (
                        <TrendingDown className="w-3 h-3 text-red-600" />
                      )}
                      <span className={`text-sm font-semibold ${pnlColor}`}>
                        {isProfit ? '+' : ''}{position.pnl_percentage?.toFixed(2) || '0.00'}%
                      </span>
                    </div>
                  </td>

                  {/* Model Confidence */}
                  <td className="px-4 py-3 whitespace-nowrap text-center">
                    {position.probability ? (
                      <span
                        className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                          position.probability >= 0.95
                            ? 'bg-green-100 text-green-800'
                            : position.probability >= 0.80
                            ? 'bg-blue-100 text-blue-800'
                            : 'bg-yellow-100 text-yellow-800'
                        }`}
                      >
                        {(position.probability * 100).toFixed(1)}%
                      </span>
                    ) : (
                      <span className="text-xs text-gray-400">N/A</span>
                    )}
                  </td>

                  {/* Closed Time */}
                  <td className="px-4 py-3 whitespace-nowrap text-left">
                    <div className="flex items-center gap-1 text-xs text-gray-600">
                      <Clock className="w-3 h-3" />
                      {position.exit_time &&
                        formatDistance(new Date(position.exit_time), new Date(), {
                          addSuffix: true,
                        })}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Summary Footer */}
      <div className="mt-4 pt-4 border-t border-gray-200 grid grid-cols-3 gap-4 text-center">
        <div>
          <div className="text-xs text-gray-600 mb-1">Total Closed</div>
          <div className="text-lg font-bold text-gray-900">{closedPositions.length}</div>
        </div>
        <div>
          <div className="text-xs text-gray-600 mb-1">Winners</div>
          <div className="text-lg font-bold text-green-600">
            {closedPositions.filter((p) => p.pnl > 0).length}
          </div>
        </div>
        <div>
          <div className="text-xs text-gray-600 mb-1">Losers</div>
          <div className="text-lg font-bold text-red-600">
            {closedPositions.filter((p) => p.pnl <= 0).length}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ClosedPositions;
