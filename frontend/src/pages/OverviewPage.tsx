import { Server, Activity, AlertTriangle, Zap } from 'lucide-react';
import DashboardCard from '../components/shared/DashboardCard';
import SystemHealthHeatmap from '../components/shared/SystemHealthHeatmap';
import LiveEventStream from '../components/shared/LiveEventStream';
import PipelineHealthPanel from '../components/shared/PipelineHealthPanel';
import EventRateChart from '../components/charts/EventRateChart';
import SeverityChart from '../components/charts/SeverityChart';
import FaultTypesChart from '../components/charts/FaultTypesChart';
import SeverityBadge from '../components/shared/SeverityBadge';
import {
  systems,
  getActiveAlerts,
  getDegradedSystems,
  getCriticalAlertCount,
  formatTimestamp,
} from '../data/mockData';
import { useDashboard } from '../context/DashboardContext';

export default function OverviewPage() {
  const { filteredEvents } = useDashboard();
  const degraded = getDegradedSystems();
  const criticalAlerts = getCriticalAlertCount();
  const activeAlerts = getActiveAlerts().length;

  // Recent critical/error events from filtered set
  const recentCritical = filteredEvents
    .filter((e) => e.severity === 'CRITICAL' || e.severity === 'ERROR')
    .sort((a, b) => new Date(b.event_time).getTime() - new Date(a.event_time).getTime())
    .slice(0, 8);

  return (
    <div className="space-y-5">
      {/* Page Header */}
      <div>
        <h2 className="text-lg font-bold text-text-primary">Mission Control</h2>
        <p className="text-xs text-text-muted mt-0.5">System telemetry & alert activity overview</p>
      </div>

      {/* ── Top Row: KPI Strip ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <DashboardCard
            title="Systems Online"
            value={systems.filter(s => s.status === 'online').length}
            subtitle={degraded > 0 ? `${degraded} degraded` : 'All healthy'}
            subtitleColor={degraded > 0 ? 'text-accent-amber' : 'text-signal-highlight'}
            icon={<Server className="w-5 h-5 text-signal-primary" />}
            iconBg="bg-signal-primary/15"
          />
          <DashboardCard
            title="Systems Degraded"
            value={degraded}
            subtitle={degraded > 0 ? 'Requires attention' : 'None'}
            subtitleColor={degraded > 0 ? 'text-accent-orange' : 'text-signal-highlight'}
            icon={<Activity className="w-5 h-5 text-accent-orange" />}
            iconBg="bg-accent-orange/15"
          />
          <DashboardCard
            title="Critical Alerts"
            value={criticalAlerts}
            subtitle={`${activeAlerts} total active`}
            subtitleColor="text-accent-red"
            icon={<AlertTriangle className="w-5 h-5 text-accent-red" />}
            iconBg="bg-accent-red/15"
            pulse={criticalAlerts > 0}
          />
          <DashboardCard
            title="Filtered Events"
            value={filteredEvents.length.toLocaleString()}
            subtitle="matching filters"
            subtitleColor="text-text-secondary"
            icon={<Zap className="w-5 h-5 text-signal-primary" />}
            iconBg="bg-signal-primary/15"
          />
        </div>
      {/* ── Second Row: Pipeline Status ── */}
      <div>
        <PipelineHealthPanel />
      </div>

      {/* ── Middle Row: Health Heatmap + Live Event Stream ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SystemHealthHeatmap />
        <LiveEventStream />
      </div>

      {/* ── Bottom Row: Event Rate + Severity + Fault Types ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <EventRateChart />
        <SeverityChart />
        <FaultTypesChart />
      </div>

      {/* Recent Critical Events */}
      {recentCritical.length > 0 && (
        <div className="glass-panel panel-glow rounded-xl p-4 animate-fade-in">
          <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider mb-3">Recent Critical Events</h3>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-1">
            {recentCritical.map((e) => (
              <div
                key={e.event_record_id}
                className={`flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-bg-hover transition-colors cursor-pointer ${
                  e.severity === 'CRITICAL' ? 'severity-border-critical' : 'severity-border-error'
                }`}
              >
                <SeverityBadge severity={e.severity} />
                <div className="flex-1 min-w-0">
                  <p className="text-xs text-text-primary truncate">{e.fault_description}</p>
                  <p className="text-[10px] text-text-muted mt-0.5">{e.hostname} · {formatTimestamp(e.event_time)}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
