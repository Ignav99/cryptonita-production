import { LogOut } from 'lucide-react';
import Badge from '../ui/Badge';
import { auth } from '../../api/client';

const statusVariant = {
  running: 'success',
  stopped: 'danger',
  paused: 'warning',
  training: 'info',
};

export default function Header({ title, botStatus, btcPrice }) {
  return (
    <header className="h-14 bg-dark-card border-b border-dark-border flex items-center justify-between px-6">
      <h1 className="text-base font-semibold text-text-primary">{title}</h1>

      <div className="flex items-center gap-4">
        {btcPrice && (
          <div className="text-sm">
            <span className="text-text-secondary">BTC </span>
            <span className="font-mono font-medium text-text-primary">
              ${Number(btcPrice).toLocaleString()}
            </span>
          </div>
        )}

        <Badge variant={statusVariant[botStatus] || 'neutral'}>
          {botStatus || 'offline'}
        </Badge>

        <button
          onClick={() => auth.logout()}
          className="p-1.5 rounded-md text-text-secondary hover:text-text-primary hover:bg-dark-hover"
          title="Logout"
        >
          <LogOut className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
}
