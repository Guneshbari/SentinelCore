import { useNavigate } from 'react-router-dom';
import { systems, events, timeAgo } from '../data/mockData';
import ResourceGauge from '../components/shared/ResourceGauge';

import type { SystemStatus } from '../types/telemetry';

const statusConfig: Record<SystemStatus, { color: string; label: string; dot: string; glow: string }> = {
  online: { color: 'text-[#22c55e]', label: 'Online', dot: 'bg-[#22c55e]', glow: 'shadow-[0_0_6px_rgba(34,197,94,0.4)]' },
  degraded: { color: 'text-[#ffd60a]', label: 'Degraded', dot: 'bg-[#ffd60a]', glow: 'shadow-[0_0_6px_rgba(255,214,10,0.4)]' },
  offline: { color: 'text-[#ff3b30]', label: 'Offline', dot: 'bg-[#ff3b30]', glow: 'shadow-[0_0_6px_rgba(255,59,48,0.4)]' },
};

export default function SystemsPage() {
  const navigate = useNavigate();

  const onlineCount = systems.filter((s) => s.status === 'online').length;
  const degradedCount = systems.filter((s) => s.status === 'degraded').length;

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-text-primary">Systems Monitor</h2>
          <p className="text-xs text-text-muted mt-0.5">Infrastructure health monitoring</p>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <span className="flex items-center gap-1.5 text-text-secondary">
            <span className="w-2 h-2 rounded-full bg-[#22c55e] shadow-[0_0_6px_rgba(34,197,94,0.4)]" />
            {onlineCount} Online
          </span>
          <span className="flex items-center gap-1.5 text-text-secondary">
            <span className="w-2 h-2 rounded-full bg-[#ffd60a] shadow-[0_0_6px_rgba(255,214,10,0.4)]" />
            {degradedCount} Degraded
          </span>
          <span className="px-2.5 py-1 rounded-lg glass-panel text-text-secondary text-[11px]">
            {systems.length} Total
          </span>
        </div>
      </div>

      {/* Systems Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {systems.map((system) => {
          const status = statusConfig[system.status];

          // Recent event info
          const systemEvents = events.filter((e) => e.system_id === system.system_id);
          const recentEvent = systemEvents.sort((a, b) => new Date(b.event_time).getTime() - new Date(a.event_time).getTime())[0];
          const eventRate5m = systemEvents.filter((e) => {
            const refTime = new Date('2026-03-08T14:25:00Z').getTime();
            return new Date(e.event_time).getTime() > refTime - 5 * 60_000;
          }).length;
          const lastFault = recentEvent?.fault_type || 'None';

          return (
            <div
              key={system.system_id}
              onClick={() => navigate(`/events?system=${system.hostname}`)}
              className="glass-panel panel-glow hover-lift rounded-xl p-5 animate-fade-in cursor-pointer group"
            >
              {/* Name and Status */}
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-text-primary group-hover:text-signal-primary transition-colors">{system.hostname}</h3>
                  <p className="text-[10px] font-mono text-text-muted mt-0.5">{system.system_id}</p>
                </div>
                <span className={`flex items-center gap-1.5 text-xs font-medium ${status.color}`}>
                  <span className={`w-2 h-2 rounded-full ${status.dot} ${status.glow}`} />
                  {status.label}
                </span>
              </div>

              {/* Gauges */}
              <div className="flex items-center justify-around mb-4">
                <div className="relative"><ResourceGauge label="CPU" value={system.cpu_usage_percent} color="#00e5ff" size={72} /></div>
                <div className="relative"><ResourceGauge label="Memory" value={system.memory_usage_percent} color="#8b5cf6" size={72} /></div>
                <div className="relative"><ResourceGauge label="Disk" value={system.disk_free_percent} color="#22c55e" size={72} /></div>
              </div>

              {/* New: Event indicators */}
              <div className="flex items-center gap-3 mb-3 text-[10px]">
                {/* Recent event indicator */}
                <div className="flex items-center gap-1.5">
                  <span className={`w-1.5 h-1.5 rounded-full ${recentEvent ? 'bg-signal-primary' : 'bg-text-muted'}`} />
                  <span className="text-text-secondary">{recentEvent ? timeAgo(recentEvent.event_time) : 'No events'}</span>
                </div>
                {/* Event rate */}
                <div className="flex items-center gap-1">
                  <span className="text-signal-primary font-semibold">{eventRate5m}</span>
                  <span className="text-text-muted">evt/5m</span>
                </div>
                {/* Last fault type */}
                <span className="text-text-muted truncate flex-1 text-right">{lastFault}</span>
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between text-[10px] text-text-muted pt-3 border-t border-border/50">
                <span>{system.os_version}</span>
                <span>Last seen: {timeAgo(system.last_seen)}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
