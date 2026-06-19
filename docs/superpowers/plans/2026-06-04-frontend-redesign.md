# Cryptonita Dashboard — Frontend Redesign & Bug Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 confirmed bugs in the trading dashboard and redesign the UI so orders, balance, and real-time bot status are clearly visible and correct.

**Architecture:** React 18 SPA (Vite) with Tailwind CSS served by FastAPI. Changes are source-only — Render builds the frontend during deployment via `scripts/render_build.sh` (`npm run build`). No local build needed.

**Tech Stack:** React 18, Vite, Tailwind CSS, TanStack React Query v5, Recharts, Lucide React, Axios

---

## Confirmed Bugs (from code analysis)

| # | File | Bug | Root Cause |
|---|------|-----|-----------|
| B1 | `Trades.jsx:33` | `LONG` action shows red (danger) instead of green | Badge variant only checks `=== 'BUY'` |
| B2 | `Overview.jsx:190-194` | V5 `LONG/SHORT` signals show gray (neutral) | Variant logic only handles `BUY`/`SELL` |
| B3 | `Overview.jsx:190` | V5 signals use wrong field — `signal_name` ignored | Should be `sig.signal_name \|\| sig.signal_type` |
| B4 | `Overview.jsx:56-57` | `long_win_rate`/`short_win_rate` never render | These fields don't exist in `DashboardStats` schema |

## Additional Improvements

| # | What | Why |
|---|------|-----|
| I1 | Show USDT available separately from total portfolio | User can't tell how much cash they have vs invested |
| I2 | Add recent trades (last 10) to Overview | User said "no se ve ninguna orden" — orders hidden in separate page |
| I3 | Overview stats: remove broken win-rate split, add today's P&L | `today_pnl` exists in schema, more useful than missing fields |

---

## File Map

| File | Action | What Changes |
|------|--------|-------------|
| `frontend/src/components/ui/Badge.jsx` | Modify | Add `long` (green) and `short` (red) variants |
| `frontend/src/pages/Trades.jsx` | Modify | Fix badge variant logic for LONG/SHORT/BUY/SELL |
| `frontend/src/pages/Overview.jsx` | Modify | Fix signals, remove broken win-rate section, add recent trades, improve balance display |
| `frontend/src/api/client.js` | Modify | Add `getPortfolioValue()` method |
| `frontend/src/context/DashboardContext.jsx` | Modify | Expose `usdt_balance`, `positions_value`, `today_pnl` from stats |

---

## Task 1 — Fix Badge Component (B1, B2 root fix)

**Files:**
- Modify: `frontend/src/components/ui/Badge.jsx`

- [ ] **Step 1.1: Add `long` and `short` variants**

Replace the entire file content:

```jsx
import clsx from 'clsx';

const variants = {
  success: 'bg-accent-green/15 text-accent-green border-accent-green/30',
  danger:  'bg-accent-red/15 text-accent-red border-accent-red/30',
  warning: 'bg-accent-yellow/15 text-accent-yellow border-accent-yellow/30',
  info:    'bg-accent-blue/15 text-accent-blue border-accent-blue/30',
  neutral: 'bg-dark-border/50 text-text-secondary border-dark-border',
  long:    'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  short:   'bg-rose-500/15 text-rose-400 border-rose-500/30',
};

export default function Badge({ variant = 'neutral', children, className }) {
  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border',
        variants[variant] ?? variants.neutral,
        className
      )}
    >
      {children}
    </span>
  );
}
```

- [ ] **Step 1.2: Commit**

```bash
cd "frontend"
# (no build needed — Render builds on deploy)
git add frontend/src/components/ui/Badge.jsx
git commit -m "fix: add long/short variants to Badge component"
```

---

## Task 2 — Fix Trades Page (Bug B1)

**Files:**
- Modify: `frontend/src/pages/Trades.jsx`

The issue is on line 33:
```jsx
// WRONG: LONG → danger (red)
<Badge variant={action === 'BUY' ? 'success' : 'danger'}>
```

Should map: BUY/LONG → `long` (green), SELL/SHORT → `short` (red).

- [ ] **Step 2.1: Fix action badge variant**

In `Trades.jsx`, replace the `action` column render function (lines 29-38):

```jsx
{
  key: 'action',
  label: 'Action',
  render: (v, row) => {
    const action = (v || row.side || '').toUpperCase();
    const variant =
      action === 'BUY' || action === 'LONG'  ? 'long'  :
      action === 'SELL' || action === 'SHORT' ? 'short' :
      'neutral';
    return <Badge variant={variant}>{action}</Badge>;
  },
},
```

- [ ] **Step 2.2: Add probability column** (after `total_value` column)

Insert after the `total_value` column definition:

```jsx
{
  key: 'probability',
  label: 'Prob',
  render: (v) => v != null ? `${(Number(v) * 100).toFixed(1)}%` : '—',
},
```

- [ ] **Step 2.3: Commit**

```bash
git add frontend/src/pages/Trades.jsx
git commit -m "fix: correct LONG/SHORT badge colors in Trades, add probability column"
```

---

## Task 3 — Fix Overview Page (Bugs B2, B3, B4 + Improvement I2, I3)

**Files:**
- Modify: `frontend/src/pages/Overview.jsx`

Current problems in Overview:
- Line 190: `(sig.signal_type || sig.action)` — V5 uses `signal_name`, not `action`
- Line 190-194: Variant logic doesn't handle LONG/SHORT → shows gray
- Line 56-57: `long_win_rate`/`short_win_rate` don't exist in backend schema → never renders
- No recent trades visible (user main complaint)

- [ ] **Step 3.1: Add recent trades query**

After the existing `recentSignals` query (after line 34), add:

```jsx
const { data: recentTrades } = useQuery({
  queryKey: ['trades', 10],
  queryFn: () => dashboard.getTrades(10),
  refetchInterval: 15000,
});
```

- [ ] **Step 3.2: Expose today_pnl from stats**

After line 57 (`const openCount = ...`), replace the broken long/short win rate lines (56-57):

```jsx
// Remove these two lines:
// const longWinRate = stats?.long_win_rate;
// const shortWinRate = stats?.short_win_rate;

// Add this instead:
const todayPnl = stats?.today_pnl;
const usdt_available = stats?.usdt_balance;
const positions_value = stats?.positions_value;
```

- [ ] **Step 3.3: Update stat cards grid to show USDT balance**

Replace the 4-card grid (lines 70-81) with this 4-card layout showing relevant data:

```jsx
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
```

Add `DollarSign` to the lucide imports at the top (add after `Briefcase`):
```jsx
import {
  Wallet, DollarSign, TrendingUp, TrendingDown, Target, Briefcase,
  Play, Square, Pause, Signal, Cpu,
} from 'lucide-react';
```

- [ ] **Step 3.4: Remove broken LONG/SHORT win-rate section**

Delete lines 83-99 entirely (the conditional block `{(longWinRate != null || shortWinRate != null) && ...}`).

Replace with a today PnL row (only renders if data is available):

```jsx
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
```

Add `clsx` import at the top: `import clsx from 'clsx';`

- [ ] **Step 3.5: Fix Recent Signals badge (Bug B2, B3)**

Replace lines 186-195 (the Badge variant logic for signals):

```jsx
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
```

- [ ] **Step 3.6: Add Recent Trades section**

In the right column (inside `<div className="space-y-4">`), after the Recent Signals card (after line 202), add:

```jsx
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
```

Add `ArrowRightLeft` to lucide imports: add it to the existing import list.

- [ ] **Step 3.7: Commit**

```bash
git add frontend/src/pages/Overview.jsx
git commit -m "fix: correct V5 LONG/SHORT signal badges, add recent orders to overview, show USDT balance"
```

---

## Task 4 — Add portfolio-value to API client (Improvement I1)

**Files:**
- Modify: `frontend/src/api/client.js`

The `/api/dashboard/portfolio-value` endpoint exists but isn't called from the frontend.

- [ ] **Step 4.1: Add getPortfolioValue to dashboard API object**

After `getReviewReports` (line 137), add:

```js
getPortfolioValue: async () => {
  const response = await apiClient.get('/dashboard/portfolio-value');
  return response.data;
},
```

- [ ] **Step 4.2: Commit**

```bash
git add frontend/src/api/client.js
git commit -m "feat: expose portfolio-value endpoint in API client"
```

---

## Task 5 — Fix DashboardContext (expose usdt_balance, positions_value)

**Files:**
- Modify: `frontend/src/context/DashboardContext.jsx`

`DashboardStats` schema already returns `usdt_balance` and `positions_value`. We just need to expose them from context.

- [ ] **Step 5.1: Expose usdt_balance and positions_value from stats**

The context value object (lines 41-48) already passes `stats` — no change needed there. `Overview.jsx` accesses `stats?.usdt_balance` directly (Task 3 already does this).

**Verify**: The `stats` object from the API already includes `usdt_balance` and `positions_value` (confirmed in `DashboardStats` Pydantic schema). No context change needed.

- [ ] **Step 5.2: Commit** (skip if no changes needed)

---

## Task 6 — Deploy

- [ ] **Step 6.1: Push to main (triggers Render deploy)**

```bash
git push origin main
```

Render will run `scripts/render_build.sh`:
1. `pip install -r requirements.txt`
2. `cd frontend && npm install && npm run build`
3. FastAPI serves `frontend/dist/` at `/static` and `/assets`

- [ ] **Step 6.2: Verify deploy in Render logs**

Expected log sequence:
```
🚀 Starting Render build process...
📦 Installing Python dependencies...
🎨 Building frontend...
✅ Build completed successfully!
```

Then check the deployed dashboard:
- Trades page: LONG badges should be green, SHORT badges should be red
- Overview: Recent Orders section visible, USDT Available stat card shows cash balance
- Overview: Signal badges show LONG=green, SHORT=red, HOLD=gray

---

## Self-Review Checklist

**Spec coverage:**
- [x] B1: Trades LONG/SHORT colors — covered in Task 2
- [x] B2: Overview signals LONG/SHORT → neutral — covered in Task 3.5
- [x] B3: Overview signals missing `signal_name` field — covered in Task 3.5
- [x] B4: Broken long/short win-rate section removed — covered in Task 3.4
- [x] I1: USDT available shown — covered in Task 3.3
- [x] I2: Recent orders on Overview — covered in Task 3.6
- [x] I3: Today's PnL shown — covered in Task 3.4

**Placeholder scan:** No TBD/TODO/placeholder text in any task. All code is complete.

**Type consistency:**
- `Badge` `variant` prop: added `long` and `short` → used in Tasks 2, 3, and correctly references new Badge variants
- `ArrowRightLeft` icon: imported in Task 3.6, used in same task
- `DollarSign` icon: imported in Task 3.3, used in same task
- `dashboard.getTrades(10)` in Task 3.1 — method exists in `client.js` line 92
- `stats?.usdt_balance` in Task 3.3 — field exists in `DashboardStats` Pydantic schema line 14
- `stats?.today_pnl` in Task 3.2 — field exists in `DashboardStats` Pydantic schema line 21
