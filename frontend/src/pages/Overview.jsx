import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Wallet, DollarSign, TrendingUp, TrendingDown, Target, Briefcase,
  Play, Square, Pause, Signal, Cpu, ArrowRightLeft, RefreshCcw,
} from 'lucide-react';
import clsx from 'clsx';
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

  const { data: recentTrades } = useQuery({
    queryKey: ['trades', 10],
    queryFn: () => dashboard.getTrades(10),
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

  const recalibrate = useMutation({
    mutationFn: () => dashboard.recalibratePortfolio(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stats'] });
      queryClient.invalidateQueries({ queryKey: ['positions'] });
      queryClient.invalidateQueries({ queryKey: ['trades'] });
      queryClient.invalidateQueries({ queryKey: ['performance'] });
    },
  });

  const balance = stats?.portfolio_value ?? stats?.balance ?? stats?.total_balance;
  const totalPnl = stats?.total_pnl ?? stats?.realized_pnl;
  const winRate = stats?.win_rate;
  const openCount = stats?.active_positions ?? stats?.open_positions ?? 0;

  const todayPnl = stats?.today_pnl;
  const usdt_available = stats?.usdt_balance;
  const positions_value = stats?.positions_value;

  return (
    <div className="space-y-6">
      {/* V5 Model Badge */}
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-purple-900/40 text-purple-400 border border-purple-800">
          <Cpu className="w-3 h-3" /> V5 Ternary · LONG / SHORT / HOLD
        </span>
        <span className="text-xs text-text-secondary">• SHORT via Binance Futures · Per-coin models</span>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Portfolio Value"
          value={balance != null ? Number(balance).toFixed(2) : '—'}
          prefix="$"
          icon={Wallet}
        />
        <StatCard
          label="USDT Available"
          value={usdt_available != null ? Number(usdt_available).toFixed(2) : '—'}
          prefix="$"
          icon={DollarSign}
        />
        <StatCard
          label="Total PnL"
          value={totalPnl != null ? Number(totalPnl).toFixed(2) : '—'}
          prefix="$"
          icon={TrendingUp}
          change={totalPnl != null ? Number(Number(totalPnl).toFixed(2)) : undefined}
        />
        <StatCard
          label="Win Rate"
          value={winRate != null ? Number(winRate).toFixed(1) : '—'}
          suffix="%"
          icon={Target}
        />
      </div>

      {todayPnl != null && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-dark-card border border-dark-border">
          <span className="text-xs text-text-secondary uppercase tracking-wide font-medium">Today's PnL</span>
          <span className={clsx(
            'text-sm font-bold ml-auto',
            Number(todayPnl) >= 0 ? 'text-accent-green' : 'text-accent-red'
          )}>
            {Number(todayPnl) >= 0 ? '+' : ''}{Number(todayPnl).toFixed(2)} USDT
          </span>
        </div>
      )}

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
              <div className="pt-2 border-t border-dark-border">
                <Button
                  variant="ghost"
                  size="sm"
                  icon={RefreshCcw}
                  loading={recalibrate.isPending}
                  onClick={() => recalibrate.mutate()}
                  className="w-full text-text-secondary hover:text-accent-blue"
                >
                  {recalibrate.isSuccess ? '✓ Recalibrated' : 'Recalibrate Portfolio'}
                </Button>
                {recalibrate.isError && (
                  <p className="text-xs text-accent-red mt-1">Failed to recalibrate</p>
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
                    {(() => {
                      const sigAction = (sig.signal_name || sig.signal_type || '').toUpperCase();
                      const variant =
                        sigAction === 'BUY'  || sigAction === 'LONG'  ? 'long'  :
                        sigAction === 'SELL' || sigAction === 'SHORT'  ? 'short' :
                        'neutral';
                      return <Badge variant={variant}>{sigAction || '—'}</Badge>;
                    })()}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-text-secondary">No recent signals</p>
            )}
          </Card>

          <Card title="Recent Orders" icon={ArrowRightLeft}>
            {recentTrades && recentTrades.length > 0 ? (
              <div className="space-y-2">
                {recentTrades.map((trade, i) => {
                  const action = (trade.action || '').toUpperCase();
                  const variant =
                    action === 'BUY' || action === 'LONG'   ? 'long'  :
                    action === 'SELL' || action === 'SHORT'  ? 'short' :
                    'neutral';
                  return (
                    <div key={i} className="flex items-center justify-between py-1.5 border-b border-dark-border/50 last:border-0">
                      <div className="flex items-center gap-2">
                        <Badge variant={variant}>{action}</Badge>
                        <span className="text-sm font-medium text-text-primary">{trade.ticker}</span>
                      </div>
                      <div className="text-right">
                        <span className="text-xs text-text-secondary">
                          ${Number(trade.price).toLocaleString(undefined, { maximumFractionDigits: 4 })}
                        </span>
                        {trade.timestamp && (
                          <span className="text-xs text-text-secondary ml-2">
                            {format(new Date(trade.timestamp), 'HH:mm')}
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-text-secondary">No trades yet</p>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
