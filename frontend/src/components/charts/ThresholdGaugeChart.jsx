import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts';
import EmptyState from '../ui/EmptyState';
import { Target } from 'lucide-react';

const getBarColor = (prob, threshold) => {
  const diff = prob - threshold;
  if (diff >= 0) return '#3fb950';       // green: above threshold
  if (diff >= -0.03) return '#d29922';   // yellow: within 3%
  return '#f85149';                       // red: below threshold
};

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-dark-card border border-dark-border rounded-md px-3 py-2 shadow-lg">
      <p className="text-sm font-medium text-text-primary">{d.display_name}</p>
      <p className="text-xs text-text-secondary">
        Probability: <span className="text-accent-blue">{(d.probability * 100).toFixed(1)}%</span>
      </p>
      <p className="text-xs text-text-secondary">
        Threshold: {(d.threshold * 100).toFixed(0)}%
      </p>
      <p className="text-xs text-text-secondary">
        Distance: <span style={{ color: getBarColor(d.probability, d.threshold) }}>
          {d.distance_pct > 0 ? '+' : ''}{d.distance_pct.toFixed(1)}%
        </span>
      </p>
    </div>
  );
};

export default function ThresholdGaugeChart({ data }) {
  if (!data || data.length === 0) {
    return <EmptyState icon={Target} title="No threshold data" />;
  }

  // Top 15 coins sorted by proximity (closest first)
  const chartData = data.slice(0, 15).map((d) => ({
    ...d,
    name: d.display_name,
  }));

  const height = Math.max(300, chartData.length * 28);

  return (
    <div style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 30, left: 80, bottom: 5 }}>
          <XAxis
            type="number"
            domain={[0.5, 1.0]}
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 11, fill: '#8b949e' }}
            tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
          />
          <YAxis
            type="category"
            dataKey="name"
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 11, fill: '#c9d1d9' }}
            width={75}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(88,166,255,0.05)' }} />
          <Bar dataKey="probability" radius={[0, 4, 4, 0]} barSize={18}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={getBarColor(entry.probability, entry.threshold)} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
