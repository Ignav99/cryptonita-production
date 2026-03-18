import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Signal } from 'lucide-react';
import { dashboard } from '../api/client';
import Card from '../components/ui/Card';
import DataTable from '../components/ui/DataTable';
import Badge from '../components/ui/Badge';
import SignalDistribution from '../components/charts/SignalDistribution';
import { format } from 'date-fns';

export default function Signals() {
  const [filter, setFilter] = useState('ALL');

  const { data: signals } = useQuery({
    queryKey: ['signals'],
    queryFn: () => dashboard.getSignals(100),
    refetchInterval: 15000,
  });

  const filtered = signals?.filter(
    (s) => filter === 'ALL' || s.action === filter
  );

  const columns = [
    {
      key: 'timestamp',
      label: 'Time',
      render: (v) => v ? format(new Date(v), 'MMM dd HH:mm') : '—',
    },
    { key: 'ticker', label: 'Ticker', render: (v, row) => v || row.symbol },
    {
      key: 'action',
      label: 'Action',
      render: (v) => (
        <Badge
          variant={v === 'BUY' ? 'success' : v === 'SELL' ? 'danger' : 'neutral'}
        >
          {v}
        </Badge>
      ),
    },
    {
      key: 'confidence',
      label: 'Confidence',
      render: (v) => v != null ? `${(Number(v) * 100).toFixed(1)}%` : '—',
    },
    { key: 'regime', label: 'Regime', render: (v) => v || '—' },
    {
      key: 'status',
      label: 'Status',
      render: (v) => (
        <Badge variant={v === 'executed' ? 'success' : v === 'rejected' ? 'danger' : 'neutral'}>
          {v || 'pending'}
        </Badge>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <Card
            title="Signals"
            icon={Signal}
            headerRight={
              <div className="flex gap-1">
                {['ALL', 'BUY', 'SELL', 'HOLD'].map((f) => (
                  <button
                    key={f}
                    onClick={() => setFilter(f)}
                    className={`px-2.5 py-1 rounded-md text-xs font-medium ${
                      filter === f
                        ? 'bg-accent-blue/15 text-accent-blue'
                        : 'text-text-secondary hover:text-text-primary hover:bg-dark-hover'
                    }`}
                  >
                    {f}
                  </button>
                ))}
              </div>
            }
          >
            <DataTable columns={columns} data={filtered} emptyMessage="No signals found" />
          </Card>
        </div>

        <Card title="Distribution">
          <SignalDistribution data={signals} />
        </Card>
      </div>
    </div>
  );
}
