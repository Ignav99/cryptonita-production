import clsx from 'clsx';

const statusColors = {
  running: 'bg-accent-green',
  stopped: 'bg-accent-red',
  paused: 'bg-accent-yellow',
  training: 'bg-accent-blue',
};

export default function StatusDot({ status = 'stopped' }) {
  const color = statusColors[status] || statusColors.stopped;
  const shouldPulse = status === 'running' || status === 'training';

  return (
    <span className="relative inline-flex items-center">
      {shouldPulse && (
        <span
          className={clsx('absolute inline-flex h-3 w-3 rounded-full opacity-40', color)}
          style={{ animation: 'pulse-ring 1.5s ease-out infinite' }}
        />
      )}
      <span className={clsx('relative inline-flex h-2.5 w-2.5 rounded-full', color)} />
    </span>
  );
}
