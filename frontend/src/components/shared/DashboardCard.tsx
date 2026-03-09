import type { ReactNode } from 'react';

interface DashboardCardProps {
  readonly title: string;
  readonly value: string | number;
  readonly subtitle?: string;
  readonly subtitleColor?: string;
  readonly icon: ReactNode;
  readonly iconBg?: string;
  readonly pulse?: boolean;
}

export default function DashboardCard({
  title,
  value,
  subtitle,
  subtitleColor = 'text-text-secondary',
  icon,
  iconBg = 'bg-signal-primary/15',
  pulse = false,
}: DashboardCardProps) {
  return (
    <div className="glass-panel panel-glow hover-lift rounded-xl p-5 animate-fade-in group">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-[10px] font-semibold text-text-muted uppercase tracking-[0.1em] mb-2">
            {title}
          </p>
          <p className="text-3xl font-bold text-text-primary tracking-tight">{value}</p>
          {subtitle && (
            <p className={`text-xs mt-1.5 font-medium ${subtitleColor}`}>{subtitle}</p>
          )}
        </div>
        <div className={`relative w-10 h-10 rounded-lg ${iconBg} flex items-center justify-center transition-transform duration-200 group-hover:scale-110`}>
          {icon}
          {pulse && (
            <span className="absolute -top-1 -right-1 w-3 h-3 bg-accent-red rounded-full animate-pulse-glow" />
          )}
        </div>
      </div>
    </div>
  );
}
