import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Settings as SettingsIcon, AlertTriangle, Server, Shield } from 'lucide-react';
import { controls } from '../api/client';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import Button from '../components/ui/Button';

export default function Settings() {
  const queryClient = useQueryClient();
  const [confirmReset, setConfirmReset] = useState(false);

  const { data: config } = useQuery({
    queryKey: ['config'],
    queryFn: controls.getConfig,
  });

  const resetDb = useMutation({
    mutationFn: controls.resetDatabase,
    onSuccess: () => {
      setConfirmReset(false);
      queryClient.invalidateQueries();
    },
  });

  const configEntries = config
    ? Object.entries(config).filter(([k]) => !k.startsWith('_'))
    : [];

  return (
    <div className="space-y-4">
      {/* Trading Mode */}
      <Card title="Trading Mode" icon={Shield}>
        <div className="flex items-center gap-3">
          <Badge variant={config?.testnet || config?.trading_mode === 'testnet' ? 'warning' : 'danger'}>
            {config?.testnet || config?.trading_mode === 'testnet' ? 'TESTNET' : 'PRODUCTION'}
          </Badge>
          <span className="text-sm text-text-secondary">
            {config?.testnet || config?.trading_mode === 'testnet'
              ? 'Trading with simulated funds on Binance Testnet'
              : 'Live trading with real funds'}
          </span>
        </div>
      </Card>

      {/* Bot Configuration */}
      <Card title="Bot Configuration" icon={Server}>
        {configEntries.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {configEntries.map(([key, value]) => (
              <div key={key} className="py-2">
                <span className="text-xs text-text-secondary block mb-0.5">
                  {key.replace(/_/g, ' ').toUpperCase()}
                </span>
                <span className="text-sm text-text-primary font-medium break-all">
                  {typeof value === 'boolean'
                    ? value ? 'Enabled' : 'Disabled'
                    : typeof value === 'object'
                    ? JSON.stringify(value)
                    : String(value)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-text-secondary">Loading configuration...</p>
        )}
      </Card>

      {/* Danger Zone */}
      <Card title="Danger Zone" icon={AlertTriangle}>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-text-primary">Reset Database</p>
            <p className="text-xs text-text-secondary mt-0.5">
              Delete all positions, signals, and trades. This cannot be undone.
            </p>
          </div>
          {confirmReset ? (
            <div className="flex gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setConfirmReset(false)}
              >
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                loading={resetDb.isPending}
                onClick={() => resetDb.mutate()}
              >
                Confirm Reset
              </Button>
            </div>
          ) : (
            <Button
              variant="danger"
              size="sm"
              icon={AlertTriangle}
              onClick={() => setConfirmReset(true)}
            >
              Reset Database
            </Button>
          )}
        </div>
      </Card>
    </div>
  );
}
