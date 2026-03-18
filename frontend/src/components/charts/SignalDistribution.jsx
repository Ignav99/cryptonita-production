import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import EmptyState from '../ui/EmptyState';
import { Signal } from 'lucide-react';

const COLORS = {
  BUY: '#3fb950',
  SELL: '#f85149',
  HOLD: '#8b949e',
};

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-dark-card border border-dark-border rounded-md px-3 py-2 shadow-lg">
      <p className="text-sm font-medium" style={{ color: payload[0].payload.fill }}>
        {payload[0].name}: {payload[0].value}
      </p>
    </div>
  );
};

export default function SignalDistribution({ data }) {
  if (!data || data.length === 0) {
    return <EmptyState icon={Signal} title="No signal data" />;
  }

  const counts = data.reduce((acc, s) => {
    const action = s.action || 'HOLD';
    acc[action] = (acc[action] || 0) + 1;
    return acc;
  }, {});

  const chartData = Object.entries(counts).map(([name, value]) => ({
    name,
    value,
    fill: COLORS[name] || '#8b949e',
  }));

  return (
    <div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={45}
              outerRadius={70}
              dataKey="value"
              stroke="none"
            >
              {chartData.map((entry) => (
                <Cell key={entry.name} fill={entry.fill} />
              ))}
            </Pie>
            <Tooltip content={<CustomTooltip />} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="flex justify-center gap-4 mt-2">
        {chartData.map((entry) => (
          <div key={entry.name} className="flex items-center gap-1.5 text-xs">
            <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: entry.fill }} />
            <span className="text-text-secondary">
              {entry.name} ({entry.value})
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
