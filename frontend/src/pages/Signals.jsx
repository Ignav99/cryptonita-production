import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Signal, BarChart3, TrendingUp, Target, Activity, ArrowUp, ArrowDown, Minus } from 'lucide-react';
import { dashboard } from '../api/client';
import Card from '../components/ui/Card';
import DataTable from '../components/ui/DataTable';
import Badge from '../components/ui/Badge';
import StatCard from '../components/ui/StatCard';
import SignalDistribution from '../components/charts/SignalDistribution';
import ProbabilityTrendChart from '../components/charts/ProbabilityTrendChart';
import ThresholdGaugeChart from '../components/charts/ThresholdGaugeChart';
import { format } from 'date-fns';

const TABS = [
  { key: 'overview', label: 'Overview', icon: BarChart3 },
  { key: 'signals', label: 'All Signals', icon: Signal },
  { key: 'trends', label: 'Trends', icon: TrendingUp },
  { key: 'thresholds', label: 'Thresholds', icon: Target },
];

const TIER_LABELS = { 1: 'Blue Chip', 2: 'Large Cap', 3: 'Mid Cap', 4: 'Meme' };
const TIER_COLORS = { 1: 'info', 2: 'success', 3: 'warning', 4: 'danger' };

function TrendArrow({ direction }) {
  if (direction === 'up') return <ArrowUp className="w-3.5 h-3.5 text-accent-green" />;
  if (direction === 'down') return <ArrowDown className="w-3.5 h-3.5 text-accent-red" />;
  return <Minus className="w-3.5 h-3.5 text-text-secondary" />;
}

function DistanceBadge({ value }) {
  const pct = (value * 100).toFixed(1);
  const variant = value >= 0 ? 'success' : value >= -0.03 ? 'warning' : 'danger';
  return <Badge variant={variant}>{value > 0 ? '+' : ''}{pct}%</Badge>;
}

export default function Signals() {
  const [tab, setTab] = useState('overview');
  const [signalFilter, setSignalFilter] = useState('ALL');
  const [tierFilter, setTierFilter] = useState('ALL');
  const [selectedTickers, setSelectedTickers] = useState([]);

  const { data: summary, isLoading: loadingSummary, error: errorSummary } = useQuery({
    queryKey: ['signals-summary'],
    queryFn: () => dashboard.getSignalsSummary(),
    refetchInterval: 30000,
  });

  const { data: coins, isLoading: loadingCoins, error: errorCoins } = useQuery({
    queryKey: ['signals-coins'],
    queryFn: () => dashboard.getCoinSummaries(),
    refetchInterval: 30000,
  });

  const { data: signals, isLoading: loadingSignals, error: errorSignals } = useQuery({
    queryKey: ['signals-all'],
    queryFn: () => dashboard.getSignals(200),
    refetchInterval: 15000,
  });

  const { data: thresholds, isLoading: loadingThresholds, error: errorThresholds } = useQuery({
    queryKey: ['signals-thresholds'],
    queryFn: () => dashboard.getThresholdProximity(),
    refetchInterval: 30000,
  });

  // Debug: show first error in a banner
  const firstError = errorSummary || errorCoins || errorSignals || errorThresholds;
  const isLoading = loadingSummary || loadingCoins;

  const trendTickers = selectedTickers.length > 0
    ? selectedTickers.join(',')
    : coins?.slice(0, 3).map((c) => c.ticker).join(',') || '';

  const { data: trends } = useQuery({
    queryKey: ['signals-trends', trendTickers],
    queryFn: () => dashboard.getSignalTrends(14, trendTickers || null),
    refetchInterval: 60000,
    enabled: tab === 'trends' || tab === 'overview',
  });

  // Filtered data
  const filteredSignals = signals?.filter((s) => {
    if (signalFilter !== 'ALL' && s.signal_type !== signalFilter) return false;
    return true;
  });

  const filteredCoins = coins?.filter((c) => {
    if (signalFilter !== 'ALL' && c.latest_signal_type !== signalFilter) return false;
    if (tierFilter !== 'ALL' && c.tier !== Number(tierFilter)) return false;
    return true;
  });

  // Coin summary columns
  const coinColumns = [
    {
      key: 'display_name',
      label: 'Coin',
      render: (v, row) => (
        <div>
          <span className="font-medium text-text-primary">{v}</span>
          <span className="text-xs text-text-secondary ml-1.5">{row.ticker.replace('USDT', '')}</span>
        </div>
      ),
    },
    {
      key: 'latest_signal_type',
      label: 'Signal',
      render: (v) => (
        <Badge variant={v === 'BUY' ? 'success' : v === 'SELL' ? 'danger' : 'neutral'}>
          {v}
        </Badge>
      ),
    },
    {
      key: 'latest_probability',
      label: 'Probability',
      render: (v) => (
        <span className="font-mono text-sm">{(v * 100).toFixed(1)}%</span>
      ),
    },
    {
      key: 'threshold',
      label: 'Threshold',
      render: (v) => (
        <span className="font-mono text-xs text-text-secondary">{(v * 100).toFixed(0)}%</span>
      ),
    },
    {
      key: 'distance_to_threshold',
      label: 'Distance',
      render: (v) => <DistanceBadge value={v} />,
    },
    {
      key: 'trend_direction',
      label: 'Trend',
      render: (v) => <TrendArrow direction={v} />,
    },
    {
      key: 'tier',
      label: 'Tier',
      render: (v) => (
        <Badge variant={TIER_COLORS[v] || 'neutral'}>
          {TIER_LABELS[v] || `T${v}`}
        </Badge>
      ),
    },
  ];

  // All signals columns
  const signalColumns = [
    {
      key: 'timestamp',
      label: 'Time',
      render: (v) => v ? format(new Date(v), 'MMM dd HH:mm') : '—',
    },
    {
      key: 'display_name',
      label: 'Coin',
      render: (v, row) => (
        <span className="font-medium">{v || row.ticker}</span>
      ),
    },
    {
      key: 'signal_type',
      label: 'Signal',
      render: (v) => (
        <Badge variant={v === 'BUY' ? 'success' : v === 'SELL' ? 'danger' : 'neutral'}>
          {v}
        </Badge>
      ),
    },
    {
      key: 'probability',
      label: 'Probability',
      render: (v) => (
        <span className="font-mono text-sm">{(v * 100).toFixed(1)}%</span>
      ),
    },
    {
      key: 'threshold',
      label: 'Threshold',
      render: (v) => (
        <span className="font-mono text-xs text-text-secondary">{(v * 100).toFixed(0)}%</span>
      ),
    },
    {
      key: 'distance_to_threshold',
      label: 'Distance',
      render: (v) => <DistanceBadge value={v} />,
    },
  ];

  // Threshold table for "near threshold" coins
  const nearThresholdCoins = thresholds?.filter((t) => Math.abs(t.distance_pct) <= 5) || [];

  // Tier stats for thresholds tab
  const tierStats = [1, 2, 3, 4].map((tier) => {
    const tierCoins = thresholds?.filter((t) => t.tier === tier) || [];
    const avgProb = tierCoins.length > 0
      ? tierCoins.reduce((s, c) => s + c.probability, 0) / tierCoins.length
      : 0;
    return { tier, count: tierCoins.length, avgProb };
  });

  // Ticker selection for trends tab
  const toggleTicker = (ticker) => {
    setSelectedTickers((prev) => {
      if (prev.includes(ticker)) return prev.filter((t) => t !== ticker);
      if (prev.length >= 5) return prev;
      return [...prev, ticker];
    });
  };

  return (
    <div className="space-y-4">
      {/* Error Banner */}
      {firstError && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-4 py-3">
          <p className="text-sm text-red-400 font-medium">API Error</p>
          <p className="text-xs text-red-400/80 mt-0.5">
            {firstError.response?.data?.detail || firstError.message || 'Failed to fetch signals data'}
          </p>
        </div>
      )}
      {/* Loading Banner */}
      {isLoading && !firstError && (
        <div className="bg-accent-blue/10 border border-accent-blue/30 rounded-lg px-4 py-3">
          <p className="text-sm text-accent-blue">Loading signals data...</p>
        </div>
      )}
      {/* Stat Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Coins Scanned"
          value={summary?.total_coins_scanned ?? '—'}
          icon={Activity}
        />
        <StatCard
          label="BUY Signals"
          value={summary?.buy_signals_count ?? '—'}
          icon={Signal}
        />
        <StatCard
          label="Near Threshold"
          value={summary?.near_threshold_count ?? '—'}
          icon={Target}
        />
        <StatCard
          label="Avg Probability"
          value={summary?.avg_probability != null ? `${(summary.avg_probability * 100).toFixed(1)}%` : '—'}
          icon={TrendingUp}
        />
      </div>

      {/* Tab Navigation */}
      <div className="flex gap-1 bg-dark-card border border-dark-border rounded-lg p-1">
        {TABS.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                tab === t.key
                  ? 'bg-accent-blue/15 text-accent-blue'
                  : 'text-text-secondary hover:text-text-primary hover:bg-dark-hover'
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {t.label}
            </button>
          );
        })}
      </div>

      {/* =============== OVERVIEW TAB =============== */}
      {tab === 'overview' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <Card
              title="Coin Summary"
              icon={BarChart3}
              headerRight={
                <div className="flex gap-1">
                  {['ALL', 'BUY', 'HOLD'].map((f) => (
                    <button
                      key={f}
                      onClick={() => setSignalFilter(f)}
                      className={`px-2.5 py-1 rounded-md text-xs font-medium ${
                        signalFilter === f
                          ? 'bg-accent-blue/15 text-accent-blue'
                          : 'text-text-secondary hover:text-text-primary hover:bg-dark-hover'
                      }`}
                    >
                      {f}
                    </button>
                  ))}
                  <span className="mx-1 border-l border-dark-border" />
                  {['ALL', '1', '2', '3', '4'].map((t) => (
                    <button
                      key={t}
                      onClick={() => setTierFilter(t)}
                      className={`px-2 py-1 rounded-md text-xs font-medium ${
                        tierFilter === t
                          ? 'bg-accent-blue/15 text-accent-blue'
                          : 'text-text-secondary hover:text-text-primary hover:bg-dark-hover'
                      }`}
                    >
                      {t === 'ALL' ? 'All Tiers' : `T${t}`}
                    </button>
                  ))}
                </div>
              }
            >
              <DataTable
                columns={coinColumns}
                data={filteredCoins}
                emptyMessage="No coins found"
              />
            </Card>
          </div>
          <div className="space-y-4">
            <Card title="Signal Distribution">
              <SignalDistribution data={coins} />
            </Card>
            {summary?.highest_probability_ticker && (
              <Card title="Top Signal">
                <div className="text-center py-4">
                  <p className="text-2xl font-bold text-accent-green">
                    {(summary.highest_probability_value * 100).toFixed(1)}%
                  </p>
                  <p className="text-sm text-text-secondary mt-1">
                    {summary.highest_probability_ticker}
                  </p>
                  {summary.last_scan_time && (
                    <p className="text-xs text-text-secondary mt-2">
                      Last scan: {format(new Date(summary.last_scan_time), 'MMM dd HH:mm')}
                    </p>
                  )}
                </div>
              </Card>
            )}
          </div>
        </div>
      )}

      {/* =============== ALL SIGNALS TAB =============== */}
      {tab === 'signals' && (
        <Card
          title="All Signals"
          icon={Signal}
          headerRight={
            <div className="flex gap-1">
              {['ALL', 'BUY', 'SELL', 'HOLD'].map((f) => (
                <button
                  key={f}
                  onClick={() => setSignalFilter(f)}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium ${
                    signalFilter === f
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
          <DataTable
            columns={signalColumns}
            data={filteredSignals}
            emptyMessage="No signals found"
          />
        </Card>
      )}

      {/* =============== TRENDS TAB =============== */}
      {tab === 'trends' && (
        <div className="space-y-4">
          <Card title="Select Coins (max 5)">
            <div className="flex flex-wrap gap-2">
              {coins?.map((c) => (
                <button
                  key={c.ticker}
                  onClick={() => toggleTicker(c.ticker)}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium border transition-colors ${
                    selectedTickers.includes(c.ticker)
                      ? 'border-accent-blue bg-accent-blue/15 text-accent-blue'
                      : 'border-dark-border text-text-secondary hover:text-text-primary hover:bg-dark-hover'
                  }`}
                >
                  {c.display_name}
                </button>
              ))}
            </div>
          </Card>
          <Card title="Probability Trends (14 days)" icon={TrendingUp}>
            <ProbabilityTrendChart trends={trends} />
          </Card>
        </div>
      )}

      {/* =============== THRESHOLDS TAB =============== */}
      {tab === 'thresholds' && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {tierStats.map((ts) => (
              <StatCard
                key={ts.tier}
                label={TIER_LABELS[ts.tier]}
                value={ts.count}
                suffix="coins"
                icon={Target}
              />
            ))}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card title="Threshold Proximity" icon={Target}>
              <ThresholdGaugeChart data={thresholds} />
            </Card>
            <Card title="Near Threshold (within 5%)">
              <DataTable
                columns={[
                  { key: 'display_name', label: 'Coin', render: (v) => <span className="font-medium">{v}</span> },
                  {
                    key: 'signal_type',
                    label: 'Signal',
                    render: (v) => (
                      <Badge variant={v === 'BUY' ? 'success' : v === 'SELL' ? 'danger' : 'neutral'}>{v}</Badge>
                    ),
                  },
                  {
                    key: 'probability',
                    label: 'Prob',
                    render: (v) => <span className="font-mono text-sm">{(v * 100).toFixed(1)}%</span>,
                  },
                  {
                    key: 'distance_pct',
                    label: 'Distance',
                    render: (v) => {
                      const color = v >= 0 ? 'text-accent-green' : v >= -3 ? 'text-yellow-400' : 'text-accent-red';
                      return <span className={`font-mono text-sm ${color}`}>{v > 0 ? '+' : ''}{v.toFixed(1)}%</span>;
                    },
                  },
                  {
                    key: 'tier',
                    label: 'Tier',
                    render: (v) => <Badge variant={TIER_COLORS[v] || 'neutral'}>{TIER_LABELS[v]}</Badge>,
                  },
                ]}
                data={nearThresholdCoins}
                emptyMessage="No coins near threshold"
              />
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
