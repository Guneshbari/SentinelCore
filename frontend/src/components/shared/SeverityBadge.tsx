import type { Severity } from '../../types/telemetry';

const severityConfig: Record<Severity, { bg: string; text: string; label: string; glow: string }> = {
  CRITICAL: { bg: 'bg-[#ff3b30]/15', text: 'text-[#ff3b30]', label: 'Critical', glow: 'shadow-[0_0_8px_rgba(255,59,48,0.3)]' },
  ERROR: { bg: 'bg-[#ff7a18]/15', text: 'text-[#ff7a18]', label: 'Error', glow: 'shadow-[0_0_8px_rgba(255,122,24,0.3)]' },
  WARNING: { bg: 'bg-[#ffd60a]/15', text: 'text-[#ffd60a]', label: 'Warning', glow: 'shadow-[0_0_8px_rgba(255,214,10,0.2)]' },
  INFO: { bg: 'bg-[#00c2ff]/15', text: 'text-[#00c2ff]', label: 'Info', glow: 'shadow-[0_0_8px_rgba(0,194,255,0.3)]' },
};

interface SeverityBadgeProps {
  readonly severity: Severity;
  readonly size?: 'sm' | 'md';
}

export default function SeverityBadge({ severity, size = 'sm' }: SeverityBadgeProps) {
  const config = severityConfig[severity];
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-xs';

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md font-semibold ${config.bg} ${config.text} ${config.glow} ${sizeClasses}`}
    >
      <span className="w-1.5 h-1.5 rounded-full bg-current" />
      {config.label}
    </span>
  );
}

export { severityConfig };
