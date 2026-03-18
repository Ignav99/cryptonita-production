import React from 'react';
import { TrendingUp, TrendingDown, DollarSign, Target, BarChart3, Activity, Wallet, PieChart } from 'lucide-react';

const Stats = ({ stats }) => {
  if (!stats) {
    return (
      <div className="space-y-6">
        {/* Portfolio Overview Skeleton */}
        <div className="card animate-pulse">
          <div className="h-6 bg-gray-200 rounded w-1/3 mb-4"></div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="h-20 bg-gray-200 rounded"></div>
            <div className="h-20 bg-gray-200 rounded"></div>
            <div className="h-20 bg-gray-200 rounded"></div>
          </div>
        </div>

        {/* Stats Cards Skeleton */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="stat-card animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-1/2 mb-3"></div>
              <div className="h-8 bg-gray-200 rounded w-3/4"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  const statCards = [
    {
      title: 'Total P&L',
      value: `$${stats.total_pnl?.toFixed(2) || '0.00'}`,
      change: stats.total_pnl_pct || 0,
      icon: DollarSign,
      color: stats.total_pnl >= 0 ? 'green' : 'red',
    },
    {
      title: 'Win Rate',
      value: `${stats.win_rate?.toFixed(1) || '0.0'}%`,
      subtitle: `From closed positions`,
      icon: Target,
      color: stats.win_rate >= 50 ? 'green' : 'red',
    },
    {
      title: 'Open Positions',
      value: stats.active_positions || 0,
      subtitle: `Max: 10 positions`,
      icon: BarChart3,
      color: 'blue',
    },
    {
      title: 'Today',
      value: `$${stats.today_pnl?.toFixed(2) || '0.00'}`,
      change: stats.today_pnl_pct || 0,
      icon: Activity,
      color: stats.today_pnl >= 0 ? 'green' : 'red',
    },
  ];

  return (
    <div className="space-y-6">
      {/* Portfolio Overview Card */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Wallet className="w-5 h-5 text-blue-600" />
          <h2 className="text-xl font-bold text-gray-800">Portfolio Overview</h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Available USDT */}
          <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-blue-700">💰 Available USDT</span>
              <Wallet className="w-4 h-4 text-blue-600" />
            </div>
            <div className="text-2xl font-bold text-blue-900">
              ${stats.usdt_balance?.toFixed(2) || '0.00'}
            </div>
            <div className="text-xs text-blue-600 mt-1">Ready to trade</div>
          </div>

          {/* Invested (Positions) */}
          <div className="p-4 bg-purple-50 rounded-lg border border-purple-200">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-purple-700">📊 Invested</span>
              <PieChart className="w-4 h-4 text-purple-600" />
            </div>
            <div className="text-2xl font-bold text-purple-900">
              ${stats.positions_value?.toFixed(2) || '0.00'}
            </div>
            <div className="text-xs text-purple-600 mt-1">
              {stats.active_positions || 0} open position{stats.active_positions !== 1 ? 's' : ''}
            </div>
          </div>

          {/* Total Portfolio */}
          <div className="p-4 bg-gradient-to-br from-green-50 to-emerald-50 rounded-lg border border-green-200">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-green-700">💼 Total Value</span>
              <TrendingUp className="w-4 h-4 text-green-600" />
            </div>
            <div className="text-2xl font-bold text-green-900">
              ${stats.portfolio_value?.toFixed(2) || '0.00'}
            </div>
            <div className="flex items-center gap-1 mt-1">
              {stats.total_pnl >= 0 ? (
                <TrendingUp className="w-3 h-3 text-green-600" />
              ) : (
                <TrendingDown className="w-3 h-3 text-red-600" />
              )}
              <span className={`text-xs font-semibold ${stats.total_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {stats.total_pnl >= 0 ? '+' : ''}${stats.total_pnl?.toFixed(2)} ({stats.total_pnl >= 0 ? '+' : ''}{stats.total_pnl_pct?.toFixed(2)}%)
              </span>
            </div>
          </div>
        </div>

        {/* Additional Info */}
        <div className="mt-4 p-3 bg-gray-50 rounded-lg border border-gray-200">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            <div>
              <div className="text-xs text-gray-600">Realized P&L</div>
              <div className={`text-sm font-semibold ${stats.realized_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                ${stats.realized_pnl?.toFixed(2) || '0.00'}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-600">Unrealized P&L</div>
              <div className={`text-sm font-semibold ${stats.unrealized_pnl >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                ${stats.unrealized_pnl?.toFixed(2) || '0.00'}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-600">Total Trades</div>
              <div className="text-sm font-semibold text-gray-900">
                {stats.executed_trades || 0}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-600">Win Rate</div>
              <div className={`text-sm font-semibold ${stats.win_rate >= 50 ? 'text-green-600' : 'text-red-600'}`}>
                {stats.win_rate?.toFixed(1)}%
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {statCards.map((stat, index) => {
          const Icon = stat.icon;
          const isPositive = stat.change !== undefined ? stat.change >= 0 : true;

          return (
            <div key={index} className="stat-card">
              <div className="flex items-center justify-between mb-3">
                <span className="text-sm font-medium text-gray-600">{stat.title}</span>
                <Icon
                  className={`w-5 h-5 ${
                    stat.color === 'green'
                      ? 'text-green-600'
                      : stat.color === 'red'
                      ? 'text-red-600'
                      : 'text-blue-600'
                  }`}
                />
              </div>

              <div className="text-2xl font-bold text-gray-900 mb-1">{stat.value}</div>

              {stat.change !== undefined && (
                <div className="flex items-center gap-1">
                  {isPositive ? (
                    <TrendingUp className="w-4 h-4 text-green-600" />
                  ) : (
                    <TrendingDown className="w-4 h-4 text-red-600" />
                  )}
                  <span
                    className={`text-sm font-medium ${
                      isPositive ? 'text-green-600' : 'text-red-600'
                    }`}
                  >
                    {isPositive ? '+' : ''}
                    {stat.change.toFixed(2)}%
                  </span>
                </div>
              )}

              {stat.subtitle && (
                <div className="text-xs text-gray-500 mt-1">{stat.subtitle}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default Stats;
