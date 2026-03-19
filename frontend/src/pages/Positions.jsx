import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Briefcase } from 'lucide-react';
import { dashboard } from '../api/client';
import Card from '../components/ui/Card';
import DataTable from '../components/ui/DataTable';
import Badge from '../components/ui/Badge';
import clsx from 'clsx';
import { format } from 'date-fns';

export default function Positions() {
  const [tab, setTab] = useState('open');

  const { data: openPositions } = useQuery({
    queryKey: ['positions'],
    queryFn: dashboard.getPositions,
    refetchInterval: 10000,
  });

  const { data: closedPositions } = useQuery({
    queryKey: ['closedPositions'],
    queryFn: () => dashboard.getClosedPositions(50),
    refetchInterval: 30000,
  });

  const openColumns = [
    { key: 'ticker', label: 'Ticker', render: (v, row) => v || row.symbol },
    {
      key: 'ticker',
      label: 'Side',
      render: () => (
        <Badge variant="success">LONG</Badge>
      ),
    },
    { key: 'avg_buy_price', label: 'Entry', render: (v) => v != null ? `$${Number(v).toFixed(4)}` : '—' },
    { key: 'current_price', label: 'Current', render: (v) => v != null ? `$${Number(v).toFixed(4)}` : '—' },
    {
      key: 'pnl_percentage',
      label: 'PnL',
      render: (v, row) => {
        const pnl = v ?? row.pnl;
        if (pnl == null) return '—';
        const num = Number(pnl);
        return (
          <span className={clsx(num >= 0 ? 'text-accent-green' : 'text-accent-red')}>
            {num >= 0 ? '+' : ''}{num.toFixed(2)}%
          </span>
        );
      },
    },
    {
      key: 'total_value',
      label: 'Value',
      render: (v) => v != null ? `$${Number(v).toFixed(2)}` : '—',
    },
    {
      key: 'stop_loss',
      label: 'SL',
      render: (v) => v != null ? `$${Number(v).toFixed(4)}` : '—',
    },
    {
      key: 'tp1_hit',
      label: 'TP',
      render: (v, row) => {
        const tp1 = row.tp1_hit ? '1' : '';
        const tp2 = row.tp2_hit ? '2' : '';
        const tp3 = row.tp3_hit ? '3' : '';
        const hits = [tp1, tp2, tp3].filter(Boolean).join(',');
        return hits ? (
          <Badge variant="success">TP{hits}</Badge>
        ) : (
          <span className="text-text-tertiary">—</span>
        );
      },
    },
    {
      key: 'entry_time',
      label: 'Opened',
      render: (v) => v ? format(new Date(v), 'MMM dd HH:mm') : '—',
    },
  ];

  const closedColumns = [
    { key: 'ticker', label: 'Ticker', render: (v, row) => v || row.symbol },
    {
      key: 'ticker',
      label: 'Side',
      render: () => (
        <Badge variant="success">LONG</Badge>
      ),
    },
    { key: 'entry_price', label: 'Entry', render: (v) => v != null ? `$${Number(v).toFixed(4)}` : '—' },
    { key: 'exit_price', label: 'Exit', render: (v) => v != null ? `$${Number(v).toFixed(4)}` : '—' },
    {
      key: 'pnl_percentage',
      label: 'PnL',
      render: (v, row) => {
        const pnl = v ?? row.pnl;
        if (pnl == null) return '—';
        const num = Number(pnl);
        return (
          <span className={clsx(num >= 0 ? 'text-accent-green' : 'text-accent-red')}>
            {num >= 0 ? '+' : ''}{num.toFixed(2)}%
          </span>
        );
      },
    },
    {
      key: 'exit_time',
      label: 'Closed',
      render: (v) => v ? format(new Date(v), 'MMM dd HH:mm') : '—',
    },
  ];

  const data = tab === 'open' ? openPositions : closedPositions;
  const columns = tab === 'open' ? openColumns : closedColumns;

  return (
    <Card
      title="Positions"
      icon={Briefcase}
      headerRight={
        <div className="flex gap-1">
          {['open', 'closed'].map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={clsx(
                'px-3 py-1 rounded-md text-xs font-medium capitalize',
                tab === t
                  ? 'bg-accent-blue/15 text-accent-blue'
                  : 'text-text-secondary hover:text-text-primary hover:bg-dark-hover'
              )}
            >
              {t}
            </button>
          ))}
        </div>
      }
    >
      <DataTable
        columns={columns}
        data={data}
        emptyMessage={tab === 'open' ? 'No open positions' : 'No closed positions'}
      />
    </Card>
  );
}
