import { X } from 'lucide-react';
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import SeverityBadge from './SeverityBadge';
import { formatTimestamp } from '../../data/mockData';
import { useDashboard } from '../../context/DashboardContext';
import type { TelemetryEvent } from '../../types/telemetry';

interface EventDetailInspectorProps {
  readonly event: TelemetryEvent | null;
  readonly onClose: () => void;
}

export default function EventDetailInspector({ event, onClose }: EventDetailInspectorProps) {
  if (!event) return null;

  const { filteredEvents } = useDashboard();

  // Build correlation timeline: find other events from same system
  const systemEvents = filteredEvents
    .filter((e) => e.system_id === event.system_id)
    .sort((a, b) => new Date(a.event_time).getTime() - new Date(b.event_time).getTime());

  const correlationData = systemEvents.map((e) => ({
    time: formatTimestamp(e.event_time).split(', ')[1] || formatTimestamp(e.event_time),
    cpu: e.cpu_usage_percent,
    memory: e.memory_usage_percent,
    disk: e.disk_free_percent,
    severity: e.severity === 'CRITICAL' ? 100 : e.severity === 'ERROR' ? 75 : e.severity === 'WARNING' ? 50 : 25,
  }));

  const fields = [
    { label: 'System ID', value: event.system_id, mono: true },
    { label: 'Hostname', value: event.hostname },
    { label: 'Provider', value: event.provider_name },
    { label: 'Event ID', value: String(event.event_id), mono: true },
    { label: 'Fault Type', value: event.fault_type },
    { label: 'Log Channel', value: event.log_channel },
    { label: 'CPU', value: `${event.cpu_usage_percent}%` },
    { label: 'Memory', value: `${event.memory_usage_percent}%` },
    { label: 'Disk Free', value: `${event.disk_free_percent}%` },
    { label: 'Time', value: formatTimestamp(event.event_time) },
  ];

  return (
    <div className="glass-panel panel-glow rounded-xl overflow-hidden animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider">Event Inspector</h3>
          <SeverityBadge severity={event.severity} />
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-md text-text-muted hover:text-text-primary hover:bg-bg-hover transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Fault description */}
      <div className="px-4 py-3 border-b border-border/50">
        <p className="text-sm text-text-primary leading-relaxed">{event.fault_description}</p>
      </div>

      {/* Fields grid */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 px-4 py-3 border-b border-border/50">
        {fields.map((f) => (
          <div key={f.label} className="flex justify-between py-1.5">
            <span className="text-[11px] text-text-muted">{f.label}</span>
            <span className={`text-[11px] text-text-secondary ${f.mono ? 'font-mono' : ''}`}>
              {f.value}
            </span>
          </div>
        ))}
      </div>

      {/* Correlation Timeline */}
      <div className="px-4 py-3">
        <h4 className="text-[11px] font-semibold text-text-muted uppercase tracking-wider mb-3">
          Event Correlation Timeline — {event.hostname}
        </h4>
        <ResponsiveContainer width="100%" height={160}>
          <ComposedChart data={correlationData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="cpuCorr" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#00e5ff" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#00e5ff" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1a2230" strokeOpacity={0.25} vertical={false} />
            <XAxis dataKey="time" tick={{ fill: '#556171', fontSize: 9 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: '#556171', fontSize: 9 }} axisLine={false} tickLine={false} domain={[0, 100]} />
            <Tooltip
              contentStyle={{ backgroundColor: '#05080f', border: '1px solid #1a2230', borderRadius: 8, fontSize: 11, color: '#e6edf3' }}
            />
            <Area type="monotone" dataKey="cpu" stroke="#00e5ff" fill="url(#cpuCorr)" strokeWidth={1.5} name="CPU %" />
            <Line type="monotone" dataKey="memory" stroke="#8b5cf6" strokeWidth={1.5} dot={false} name="Memory %" />
            <Line type="monotone" dataKey="disk" stroke="#22c55e" strokeWidth={1} dot={false} strokeDasharray="4 2" name="Disk Free %" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
