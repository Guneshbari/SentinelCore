import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Search,
  Server,
  AlertTriangle,
  BarChart3,
  Shield,
} from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Overview' },
  { to: '/events', icon: Search, label: 'Events' },
  { to: '/systems', icon: Server, label: 'Systems' },
  { to: '/alerts', icon: AlertTriangle, label: 'Alerts' },
  { to: '/analytics', icon: BarChart3, label: 'Analytics' },
];

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 bottom-0 w-[220px] bg-bg-surface/80 backdrop-blur-xl border-r border-border flex flex-col z-50">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 py-5 border-b border-border">
        <div className="w-8 h-8 rounded-lg bg-signal-primary/20 flex items-center justify-center shadow-[0_0_12px_rgba(0,229,255,0.3)]">
          <Shield className="w-4.5 h-4.5 text-signal-primary" />
        </div>
        <div>
          <h1 className="text-sm font-bold text-text-primary tracking-tight">SentinelCore</h1>
          <p className="text-[10px] text-signal-primary/70 uppercase tracking-[0.12em] font-semibold">SOC Console</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-3 space-y-0.5">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                isActive
                  ? 'bg-signal-primary/15 text-signal-primary shadow-[0_0_12px_rgba(0,229,255,0.15)]'
                  : 'text-text-secondary hover:text-text-primary hover:bg-bg-hover'
              }`
            }
          >
            <Icon className="w-[18px] h-[18px]" />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-border">
        <p className="text-[11px] text-text-muted">SentinelCore v0.3.0</p>
        <p className="text-[10px] text-text-muted mt-0.5">main</p>
      </div>
    </aside>
  );
}
