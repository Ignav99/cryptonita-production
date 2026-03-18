import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { format } from 'date-fns';
import EmptyState from '../ui/EmptyState';
import { TrendingUp } from 'lucide-react';

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-dark-card border border-dark-border rounded-md px-3 py-2 shadow-lg">
      <p className="text-xs text-text-secondary">{label}</p>
      <p className="text-sm font-semibold text-accent-blue">
        ${Number(payload[0].value).toFixed(2)}
      </p>
    </div>
  );
};

export default function EquityCurve({ data }) {
  if (!data || !Array.isArray(data) || data.length === 0) {
    // Try to handle object with equity_curve field
    const points = data?.equity_curve || data?.data;
    if (!points || !Array.isArray(points) || points.length === 0) {
      return <EmptyState icon={TrendingUp} title="No performance data yet" />;
    }
    data = points;
  }

  const chartData = data.map((point) => ({
    date: point.date
      ? format(new Date(point.date), 'MMM dd')
      : point.timestamp
      ? format(new Date(point.timestamp), 'MMM dd')
      : '',
    value: Number(point.balance ?? point.equity ?? point.value ?? 0),
  }));

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 5, right: 5, left: 5, bottom: 5 }}>
          <defs>
            <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#58a6ff" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#58a6ff" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="date"
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 11, fill: '#8b949e' }}
            dy={10}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 11, fill: '#8b949e' }}
            dx={-10}
            tickFormatter={(v) => `$${v}`}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="value"
            stroke="#58a6ff"
            strokeWidth={2}
            fill="url(#equityGrad)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
