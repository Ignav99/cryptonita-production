import clsx from 'clsx';

export default function StatCard({ label, value, change, icon: Icon, prefix, suffix }) {
  const isPositive = change > 0;
  const isNegative = change < 0;

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-medium text-text-secondary uppercase tracking-wide">
          {label}
        </span>
        {Icon && <Icon className="w-4 h-4 text-text-secondary" />}
      </div>
      <div className="flex items-baseline gap-1">
        {prefix && <span className="text-sm text-text-secondary">{prefix}</span>}
        <span className="text-2xl font-bold text-text-primary">{value ?? '—'}</span>
        {suffix && <span className="text-sm text-text-secondary">{suffix}</span>}
      </div>
      {change !== undefined && change !== null && (
        <div className="mt-1">
          <span
            className={clsx(
              'text-xs font-medium',
              isPositive && 'text-accent-green',
              isNegative && 'text-accent-red',
              !isPositive && !isNegative && 'text-text-secondary'
            )}
          >
            {isPositive && '+'}{change}%
          </span>
        </div>
      )}
    </div>
  );
}
