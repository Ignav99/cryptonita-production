import React from 'react';
import { ArrowUpCircle, ArrowDownCircle } from 'lucide-react';
import { format } from 'date-fns';

const Trades = ({ trades, limit = 20 }) => {
  const displayTrades = trades?.slice(0, limit) || [];

  if (!trades || trades.length === 0) {
    return (
      <div className="card">
        <h2 className="text-xl font-bold text-gray-800 mb-4">Trade History</h2>
        <div className="text-center py-8 text-gray-500">
          <p>No trades yet</p>
          <p className="text-sm mt-2">Executed trades will appear here</p>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-gray-800">Trade History</h2>
        <span className="badge badge-info">{displayTrades.length} trades</span>
      </div>

      <div className="overflow-x-auto">
        <table className="table">
          <thead>
            <tr>
              <th>Date</th>
              <th>Ticker</th>
              <th>Action</th>
              <th>Quantity</th>
              <th>Price</th>
              <th>Total</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {displayTrades.map((trade, index) => {
              const isBuy = trade.action === 'BUY';

              return (
                <tr key={index}>
                  <td className="text-sm text-gray-600">
                    {trade.timestamp &&
                      format(new Date(trade.timestamp), 'MMM dd, HH:mm')}
                  </td>

                  <td>
                    <span className="font-semibold text-gray-900">{trade.ticker}</span>
                  </td>

                  <td>
                    <div className="flex items-center gap-1">
                      {isBuy ? (
                        <ArrowUpCircle className="w-4 h-4 text-green-600" />
                      ) : (
                        <ArrowDownCircle className="w-4 h-4 text-red-600" />
                      )}
                      <span
                        className={`font-medium ${
                          isBuy ? 'text-green-600' : 'text-red-600'
                        }`}
                      >
                        {trade.action}
                      </span>
                    </div>
                  </td>

                  <td className="font-mono text-sm">{trade.quantity?.toFixed(4)}</td>

                  <td className="font-mono text-sm">${trade.price?.toFixed(4)}</td>

                  <td className="font-mono text-sm font-semibold">
                    ${trade.total_value?.toFixed(2)}
                  </td>

                  <td>
                    <span
                      className={`badge ${
                        trade.status === 'executed'
                          ? 'badge-success'
                          : trade.status === 'pending'
                          ? 'badge-warning'
                          : 'badge-danger'
                      }`}
                    >
                      {trade.status}
                    </span>
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

export default Trades;
