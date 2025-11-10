import React from 'react';
import { TrendingUp, TrendingDown, DollarSign, Target, BarChart3, Activity } from 'lucide-react';

const Stats = ({ stats }) => {
  if (!stats) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="stat-card animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-1/2 mb-3"></div>
            <div className="h-8 bg-gray-200 rounded w-3/4"></div>
          </div>
        ))}
      </div>
    );
  }

  const statCards = [
    {
      title: 'Total P&L',
      value: `$${stats.total_pnl?.toFixed(2) || '0.00'}`,
      change: stats.total_pnl_percentage || 0,
      icon: DollarSign,
      color: stats.total_pnl >= 0 ? 'green' : 'red',
    },
    {
      title: 'Win Rate',
      value: `${stats.win_rate?.toFixed(1) || '0.0'}%`,
      subtitle: `${stats.winning_trades || 0} / ${stats.total_trades || 0} trades`,
      icon: Target,
      color: stats.win_rate >= 50 ? 'green' : 'red',
    },
    {
      title: 'Open Positions',
      value: stats.open_positions || 0,
      subtitle: `Max: ${stats.max_positions || 10}`,
      icon: BarChart3,
      color: 'blue',
    },
    {
      title: 'Today',
      value: `$${stats.daily_pnl?.toFixed(2) || '0.00'}`,
      change: stats.daily_pnl_percentage || 0,
      icon: Activity,
      color: stats.daily_pnl >= 0 ? 'green' : 'red',
    },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
      {statCards.map((stat, index) => {
        const Icon = stat.icon;
        const isPositive = stat.change >= 0;

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
  );
};

export default Stats;
