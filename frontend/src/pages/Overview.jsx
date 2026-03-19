import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Wallet,
  TrendingUp,
  Target,
  Briefcase,
  Play,
  Square,
  Pause,
  Signal,
} from 'lucide-react';
import { controls, dashboard } from '../api/client';
import { useDashboard } from '../context/DashboardContext';
import StatCard from '../components/ui/StatCard';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import Button from '../components/ui/Button';
import StatusDot from '../components/ui/StatusDot';
import EquityCurve from '../components/charts/EquityCurve';
import { useQuery } from '@tanstack/react-query';
import { format } from 'date-fns';

export default function Overview() {
  const { stats, botStatus, performance } = useDashboard();
  const queryClient = useQueryClient();
  const statusStr = botStatus?.status || 'stopped';

  const { data: recentSignals } = useQuery({
    queryKey: ['signals', 5],
    queryFn: () => dashboard.getSignals(5),
    refetchInterval: 15000,
  });

  const startBot = useMutation({
    mutationFn: () => controls.startBot('auto'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['botStatus'] }),
  });

  const stopBot = useMutation({
    mutationFn: () => controls.stopBot(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['botStatus'] }),
  });

  const pauseBot = useMutation({
    mutationFn: () => controls.pauseBot(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['botStatus'] }),
  });

  const balance = stats?.portfolio_value ?? stats?.balance ?? stats?.total_balance;
  const totalPnl = stats?.total_pnl ?? stats?.realized_pnl;
  const winRate = stats?.win_rate;
  const openCount = stats?.active_positions ?? stats?.open_positions ?? 0;

  return (
    <div className="space-y-6">
      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Balance" value={balance != null ? Number(balance).toFixed(2) : '—'} prefix="$" icon={Wallet} />
        <StatCard
          label="Total PnL"
          value={totalPnl != null ? Number(totalPnl).toFixed(2) : '—'}
          prefix="$"
          icon={TrendingUp}
          change={totalPnl != null ? Number(Number(totalPnl).toFixed(2)) : undefined}
        />
        <StatCard label="Win Rate" value={winRate != null ? Number(winRate).toFixed(1) : '—'} suffix="%" icon={Target} />
        <StatCard label="Open Positions" value={openCount} icon={Briefcase} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Equity Curve */}
        <div className="lg:col-span-2">
          <Card title="Equity Curve" icon={TrendingUp}>
            <EquityCurve data={performance} />
          </Card>
        </div>

        {/* Bot Controls + Recent Signals */}
        <div className="space-y-4">
          <Card title="Bot Controls">
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <StatusDot status={statusStr} />
                <span className="text-sm font-medium text-text-primary capitalize">{statusStr}</span>
              </div>
              <div className="flex gap-2">
                {statusStr !== 'running' && (
                  <Button
                    variant="success"
                    size="sm"
                    icon={Play}
                    loading={startBot.isPending}
                    onClick={() => startBot.mutate()}
                  >
                    Start
                  </Button>
                )}
                {statusStr === 'running' && (
                  <>
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={Pause}
                      loading={pauseBot.isPending}
                      onClick={() => pauseBot.mutate()}
                    >
                      Pause
                    </Button>
                    <Button
                      variant="danger"
                      size="sm"
                      icon={Square}
                      loading={stopBot.isPending}
                      onClick={() => stopBot.mutate()}
                    >
                      Stop
                    </Button>
                  </>
                )}
                {statusStr === 'paused' && (
                  <>
                    <Button
                      variant="success"
                      size="sm"
                      icon={Play}
                      loading={startBot.isPending}
                      onClick={() => startBot.mutate()}
                    >
                      Resume
                    </Button>
                    <Button
                      variant="danger"
                      size="sm"
                      icon={Square}
                      loading={stopBot.isPending}
                      onClick={() => stopBot.mutate()}
                    >
                      Stop
                    </Button>
                  </>
                )}
              </div>
            </div>
          </Card>

          <Card title="Recent Signals" icon={Signal}>
            {recentSignals && recentSignals.length > 0 ? (
              <div className="space-y-2">
                {recentSignals.map((sig, i) => (
                  <div key={i} className="flex items-center justify-between py-1.5 border-b border-dark-border/50 last:border-0">
                    <div>
                      <span className="text-sm font-medium text-text-primary">{sig.ticker || sig.symbol}</span>
                      <span className="text-xs text-text-secondary ml-2">
                        {sig.timestamp ? format(new Date(sig.timestamp), 'HH:mm') : ''}
                      </span>
                    </div>
                    <Badge
                      variant={
                        (sig.signal_type || sig.action) === 'BUY' ? 'success' :
                        (sig.signal_type || sig.action) === 'SELL' ? 'danger' : 'neutral'
                      }
                    >
                      {sig.signal_type || sig.action}
                    </Badge>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-text-secondary">No recent signals</p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
