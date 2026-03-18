import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Briefcase,
  Signal,
  ArrowRightLeft,
  Brain,
  Settings,
  ChevronLeft,
  ChevronRight,
  Bot,
} from 'lucide-react';
import clsx from 'clsx';
import StatusDot from '../ui/StatusDot';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/positions', icon: Briefcase, label: 'Positions' },
  { to: '/signals', icon: Signal, label: 'Signals' },
  { to: '/trades', icon: ArrowRightLeft, label: 'Trades' },
  { to: '/training', icon: Brain, label: 'Training' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export default function Sidebar({ botStatus }) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <aside
      className={clsx(
        'fixed left-0 top-0 h-screen bg-dark-sidebar border-r border-dark-border flex flex-col z-40 transition-all duration-200',
        collapsed ? 'w-16' : 'w-56'
      )}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-4 h-14 border-b border-dark-border">
        <Bot className="w-6 h-6 text-accent-blue flex-shrink-0" />
        {!collapsed && (
          <span className="text-sm font-bold text-text-primary tracking-wide">
            CRYPTONITA
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-2 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                isActive
                  ? 'bg-accent-blue/10 text-accent-blue'
                  : 'text-text-secondary hover:text-text-primary hover:bg-dark-hover'
              )
            }
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {!collapsed && <span>{label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Bot Status */}
      <div className="px-3 py-3 border-t border-dark-border">
        <div className="flex items-center gap-2 px-2">
          <StatusDot status={botStatus || 'stopped'} />
          {!collapsed && (
            <span className="text-xs text-text-secondary capitalize">
              Bot {botStatus || 'stopped'}
            </span>
          )}
        </div>
      </div>

      {/* Collapse Toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="flex items-center justify-center h-10 border-t border-dark-border text-text-secondary hover:text-text-primary hover:bg-dark-hover"
      >
        {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
      </button>
    </aside>
  );
}
