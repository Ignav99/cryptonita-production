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
