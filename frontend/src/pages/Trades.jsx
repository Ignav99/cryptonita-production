import { useQuery } from '@tanstack/react-query';
import { ArrowRightLeft, DollarSign, Hash, TrendingUp } from 'lucide-react';
import { dashboard } from '../api/client';
import Card from '../components/ui/Card';
import StatCard from '../components/ui/StatCard';
import DataTable from '../components/ui/DataTable';
import Badge from '../components/ui/Badge';
import { format } from 'date-fns';

export default function Trades() {
  const { data: trades } = useQuery({
    queryKey: ['trades'],
    queryFn: () => dashboard.getTrades(100),
    refetchInterval: 30000,
  });

  const totalTrades = trades?.length || 0;
  const totalVolume = trades?.reduce((sum, t) => sum + (Number(t.total) || Number(t.price) * Number(t.quantity) || 0), 0) || 0;

  const columns = [
    {
      key: 'timestamp',
      label: 'Time',
      render: (v) => v ? format(new Date(v), 'MMM dd HH:mm:ss') : '—',
    },
    { key: 'ticker', label: 'Ticker', render: (v, row) => v || row.symbol },
    {
      key: 'action',
      label: 'Action',
      render: (v, row) => {
        const action = v || row.side;
        return (
          <Badge variant={action === 'BUY' ? 'success' : 'danger'}>
            {action}
          </Badge>
        );
      },
    },
    {
      key: 'quantity',
      label: 'Quantity',
      render: (v) => v != null ? Number(v).toFixed(6) : '—',
    },
    {
      key: 'price',
      label: 'Price',
      render: (v) => v != null ? `$${Number(v).toLocaleString()}` : '—',
    },
    {
      key: 'total',
      label: 'Total',
      render: (v, row) => {
        const total = v || (row.price && row.quantity ? Number(row.price) * Number(row.quantity) : null);
        return total != null ? `$${Number(total).toFixed(2)}` : '—';
      },
    },
    {
      key: 'status',
      label: 'Status',
      render: (v) => (
        <Badge variant={v === 'filled' || v === 'FILLED' ? 'success' : 'neutral'}>
          {v || 'executed'}
        </Badge>
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <StatCard label="Total Trades" value={totalTrades} icon={Hash} />
        <StatCard label="Total Volume" value={totalVolume.toFixed(2)} prefix="$" icon={DollarSign} />
        <StatCard label="Recent Activity" value={trades?.[0]?.ticker || trades?.[0]?.symbol || '—'} icon={TrendingUp} />
      </div>

      <Card title="Trade History" icon={ArrowRightLeft}>
        <DataTable columns={columns} data={trades} emptyMessage="No trades recorded" />
      </Card>
    </div>
  );
}
