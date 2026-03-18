import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Brain, Play, CheckCircle, Clock } from 'lucide-react';
import { controls } from '../api/client';
import { useDashboard } from '../context/DashboardContext';
import Card from '../components/ui/Card';
import Badge from '../components/ui/Badge';
import Button from '../components/ui/Button';
import DataTable from '../components/ui/DataTable';
import StatusDot from '../components/ui/StatusDot';
import { format } from 'date-fns';

export default function Training() {
  const { trainingStatus } = useDashboard();
  const queryClient = useQueryClient();

  const triggerTraining = useMutation({
    mutationFn: controls.triggerTraining,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['trainingStatus'] }),
  });

  const activeModel = trainingStatus?.active_model;
  const history = trainingStatus?.training_history || trainingStatus?.history || [];
  const isTraining = trainingStatus?.is_training || trainingStatus?.status === 'training';
  const autoTrainConfig = trainingStatus?.auto_train_config || trainingStatus?.config;

  const historyColumns = [
    {
      key: 'version',
      label: 'Version',
      render: (v, row) => v || row.model_version || '—',
    },
    {
      key: 'trained_at',
      label: 'Date',
      render: (v, row) => {
        const d = v || row.date || row.created_at;
        return d ? format(new Date(d), 'MMM dd, yyyy HH:mm') : '—';
      },
    },
    {
      key: 'accuracy',
      label: 'Accuracy',
      render: (v, row) => {
        const acc = v ?? row.metrics?.accuracy;
        return acc != null ? `${(Number(acc) * 100).toFixed(1)}%` : '—';
      },
    },
    {
      key: 'sharpe',
      label: 'Sharpe',
      render: (v, row) => {
        const s = v ?? row.metrics?.sharpe_ratio;
        return s != null ? Number(s).toFixed(2) : '—';
      },
    },
    {
      key: 'promoted',
      label: 'Status',
      render: (v, row) => {
        const promoted = v ?? row.is_active ?? row.is_promoted;
        return promoted ? (
          <Badge variant="success">Active</Badge>
        ) : (
          <Badge variant="neutral">Archived</Badge>
        );
      },
    },
  ];

  return (
    <div className="space-y-4">
      {/* Active Model Card */}
      <Card title="Active Model" icon={Brain}>
        <div className="flex items-center justify-between">
          <div className="space-y-2">
            <div className="flex items-center gap-3">
              <StatusDot status={isTraining ? 'training' : 'running'} />
              <span className="text-sm font-medium text-text-primary">
                {isTraining ? 'Training in progress...' : activeModel?.version || activeModel?.model_version || 'No model loaded'}
              </span>
            </div>
            {activeModel && (
              <div className="flex gap-4 text-xs text-text-secondary">
                {activeModel.accuracy != null && (
                  <span>Accuracy: {(Number(activeModel.accuracy) * 100).toFixed(1)}%</span>
                )}
                {activeModel.trained_at && (
                  <span>Trained: {format(new Date(activeModel.trained_at), 'MMM dd, yyyy')}</span>
                )}
              </div>
            )}
          </div>

          <Button
            variant="primary"
            size="sm"
            icon={Play}
            loading={triggerTraining.isPending}
            disabled={isTraining}
            onClick={() => triggerTraining.mutate()}
          >
            {isTraining ? 'Training...' : 'Trigger Training'}
          </Button>
        </div>
      </Card>

      {/* Auto-train Config */}
      {autoTrainConfig && (
        <Card title="Auto-Train Configuration" icon={Clock}>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            {Object.entries(autoTrainConfig).map(([key, value]) => (
              <div key={key}>
                <span className="text-xs text-text-secondary block mb-0.5">
                  {key.replace(/_/g, ' ')}
                </span>
                <span className="text-text-primary font-medium">
                  {typeof value === 'boolean' ? (value ? 'Enabled' : 'Disabled') : String(value)}
                </span>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Training History */}
      <Card title="Training History" icon={CheckCircle}>
        <DataTable
          columns={historyColumns}
          data={history}
          emptyMessage="No training history"
        />
      </Card>
    </div>
  );
}
