import clsx from 'clsx';

export default function Card({ title, icon: Icon, children, className, headerRight }) {
  return (
    <div className={clsx('bg-dark-card border border-dark-border rounded-lg', className)}>
      {(title || headerRight) && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-dark-border">
          <div className="flex items-center gap-2">
            {Icon && <Icon className="w-4 h-4 text-text-secondary" />}
            <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
          </div>
          {headerRight}
        </div>
      )}
      <div className="p-4">{children}</div>
    </div>
  );
}
