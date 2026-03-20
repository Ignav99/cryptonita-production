import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts';
import { format } from 'date-fns';
import EmptyState from '../ui/EmptyState';
import { TrendingUp } from 'lucide-react';

const COLORS = ['#58a6ff', '#3fb950', '#d29922', '#f85149', '#bc8cff', '#79c0ff'];

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-dark-card border border-dark-border rounded-md px-3 py-2 shadow-lg">
      <p className="text-xs text-text-secondary mb-1">{label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} className="text-xs font-medium" style={{ color: p.color }}>
          {p.name}: {(p.value * 100).toFixed(1)}%
        </p>
      ))}
    </div>
  );
};

export default function ProbabilityTrendChart({ trends }) {
  if (!trends || trends.length === 0) {
    return <EmptyState icon={TrendingUp} title="No trend data" />;
  }

  // Build unified time series: merge all coins into shared timestamps
  const timeMap = {};
  trends.forEach((coin) => {
    coin.data_points.forEach((pt) => {
      const key = format(new Date(pt.timestamp), 'MMM dd HH:mm');
      if (!timeMap[key]) timeMap[key] = { date: key };
      timeMap[key][coin.ticker] = pt.probability;
    });
  });

  const chartData = Object.values(timeMap).sort(
    (a, b) => new Date(a.date) - new Date(b.date)
  );

  // Use the first coin's threshold as reference (they may differ per tier)
  const avgThreshold =
    trends.reduce((sum, t) => sum + t.threshold, 0) / trends.length;

  return (
    <div className="h-80">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 5, right: 20, left: 5, bottom: 5 }}>
          <XAxis
            dataKey="date"
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 11, fill: '#8b949e' }}
            dy={10}
          />
          <YAxis
            domain={[0.5, 1.0]}
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 11, fill: '#8b949e' }}
            dx={-10}
            tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: 11, color: '#8b949e' }}
            iconType="line"
          />
          <ReferenceLine
            y={avgThreshold}
            stroke="#d29922"
            strokeDasharray="6 3"
            label={{
              value: `Threshold ${(avgThreshold * 100).toFixed(0)}%`,
              position: 'right',
              fill: '#d29922',
              fontSize: 10,
            }}
          />
          {trends.map((coin, i) => (
            <Line
              key={coin.ticker}
              type="monotone"
              dataKey={coin.ticker}
              name={coin.display_name}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={2}
              dot={false}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
