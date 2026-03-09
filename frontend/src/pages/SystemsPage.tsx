import { useNavigate } from 'react-router-dom';
import { systems, timeAgo } from '../data/mockData';
import ResourceGauge from '../components/shared/ResourceGauge';
import { getHealthScore } from '../components/shared/SystemHealthHeatmap';
import type { SystemStatus } from '../types/telemetry';

const statusConfig: Record<SystemStatus, { color: string; label: string; dot: string; glow: string }> = {
  online: { color: 'text-[#34c759]', label: 'Online', dot: 'bg-[#34c759]', glow: 'shadow-[0_0_6px_rgba(52,199,89,0.4)]' },
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
            <span className="w-2 h-2 rounded-full bg-[#34c759] shadow-[0_0_6px_rgba(52,199,89,0.4)]" />
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
          const health = getHealthScore(system);
          return (
            <div
              key={system.system_id}
              onClick={() => navigate(`/events?system=${system.hostname}`)}
              className="glass-panel rounded-xl p-5 hover:border-border-hover transition-all duration-200 animate-fade-in cursor-pointer group"
            >
              {/* Name and Status */}
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-text-primary group-hover:text-accent-blue transition-colors">{system.hostname}</h3>
                  <p className="text-[10px] font-mono text-text-muted mt-0.5">{system.system_id}</p>
                </div>
                <span className={`flex items-center gap-1.5 text-xs font-medium ${status.color}`}>
                  <span className={`w-2 h-2 rounded-full ${status.dot} ${status.glow}`} />
                  {status.label}
                </span>
              </div>

              {/* Gauges */}
              <div className="flex items-center justify-around mb-4">
                <div className="relative"><ResourceGauge label="CPU" value={system.cpu_usage_percent} color="#0a84ff" size={72} /></div>
                <div className="relative"><ResourceGauge label="Memory" value={system.memory_usage_percent} color="#bf5af2" size={72} /></div>
                <div className="relative"><ResourceGauge label="Disk" value={system.disk_free_percent} color="#64d2ff" size={72} /></div>
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
