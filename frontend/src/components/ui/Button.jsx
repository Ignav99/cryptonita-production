import clsx from 'clsx';

const variants = {
  primary: 'bg-accent-blue hover:bg-accent-blue/80 text-white',
  success: 'bg-accent-green hover:bg-accent-green/80 text-white',
  danger: 'bg-accent-red hover:bg-accent-red/80 text-white',
  ghost: 'bg-transparent hover:bg-dark-hover text-text-secondary hover:text-text-primary border border-dark-border',
};

const sizes = {
  sm: 'px-2.5 py-1 text-xs',
  md: 'px-3.5 py-1.5 text-sm',
  lg: 'px-5 py-2.5 text-sm',
};

export default function Button({
  variant = 'primary',
  size = 'md',
  icon: Icon,
  loading,
  disabled,
  children,
  className,
  ...props
}) {
  return (
    <button
      className={clsx(
        'inline-flex items-center justify-center gap-2 rounded-md font-medium transition-all duration-150',
        'disabled:opacity-50 disabled:cursor-not-allowed',
        variants[variant],
        sizes[size],
        className
      )}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
      ) : (
        Icon && <Icon className="w-4 h-4" />
      )}
      {children}
    </button>
  );
}
