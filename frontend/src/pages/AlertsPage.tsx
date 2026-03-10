import { useState, useMemo } from 'react';
import { Check, ArrowUpRight } from 'lucide-react';
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
import SeverityBadge from '../components/shared/SeverityBadge';
import { alerts, formatTimestamp, getActiveAlerts, getAcknowledgedAlerts } from '../data/mockData';
import { useDashboard } from '../context/DashboardContext';
import type { Alert, Severity } from '../types/telemetry';

export default function AlertsPage() {
  const { filteredEvents } = useDashboard();
  const [tab, setTab] = useState<'active' | 'acknowledged'>('active');
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);

  const activeAlerts = useMemo(() => getActiveAlerts(), []);
  const ackAlerts = useMemo(() => getAcknowledgedAlerts(), []);
  const displayed = tab === 'active' ? activeAlerts : ackAlerts;

  const severityCounts = useMemo(() => {
    const counts: Record<Severity, number> = { CRITICAL: 0, ERROR: 0, WARNING: 0, INFO: 0 };
    alerts.filter((a) => !a.acknowledged).forEach((a) => counts[a.severity]++);
    return counts;
  }, []);

  const summaryCards: { severity: Severity; cssClass: string }[] = [
    { severity: 'CRITICAL', cssClass: 'severity-border-critical' },
    { severity: 'ERROR', cssClass: 'severity-border-error' },
    { severity: 'WARNING', cssClass: 'severity-border-warning' },
    { severity: 'INFO', cssClass: 'severity-border-info' },
  ];

  // Build correlated events for selected alert
  const correlatedEvents = useMemo(() => {
    if (!selectedAlert) return [];
    return filteredEvents
      .filter((e) => e.system_id === selectedAlert.system_id)
      .sort((a, b) => new Date(a.event_time).getTime() - new Date(b.event_time).getTime())
      .slice(0, 8);
  }, [selectedAlert, filteredEvents]);

  const correlationData = correlatedEvents.map((e) => ({
    time: formatTimestamp(e.event_time).split(', ')[1] || formatTimestamp(e.event_time),
    cpu: e.cpu_usage_percent,
    memory: e.memory_usage_percent,
    severity: e.severity === 'CRITICAL' ? 100 : e.severity === 'ERROR' ? 75 : e.severity === 'WARNING' ? 50 : 25,
  }));

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-text-primary">Incident Queue</h2>
          <p className="text-xs text-text-muted mt-0.5">Active alerts & incident monitoring</p>
        </div>
        <div className="flex glass-panel rounded-lg overflow-hidden">
          <button
            onClick={() => setTab('active')}
            className={`px-4 py-2 text-xs font-medium transition-colors ${
              tab === 'active' ? 'bg-signal-primary text-black shadow-[0_0_12px_rgba(0,229,255,0.3)]' : 'text-text-secondary hover:text-text-primary'
            }`}
          >Active ({activeAlerts.length})</button>
          <button
            onClick={() => setTab('acknowledged')}
            className={`px-4 py-2 text-xs font-medium transition-colors ${
              tab === 'acknowledged' ? 'bg-signal-primary text-black shadow-[0_0_12px_rgba(0,229,255,0.3)]' : 'text-text-secondary hover:text-text-primary'
            }`}
          >Acknowledged ({ackAlerts.length})</button>
        </div>
      </div>

      {/* Severity Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {summaryCards.map(({ severity, cssClass }) => (
          <div key={severity} className={`glass-panel panel-glow ${cssClass} rounded-lg px-4 py-3`}>
            <p className="text-[10px] text-text-muted uppercase tracking-wider font-semibold">{severity}</p>
            <p className="text-2xl font-bold text-text-primary mt-1">{severityCounts[severity]}</p>
          </div>
        ))}
      </div>

      {/* ── Incident Console: Alert Timeline (left) + Investigation (right) ── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        {/* Alert Timeline */}
        <div className="lg:col-span-3 glass-panel panel-glow rounded-xl p-4 space-y-1 animate-fade-in">
          <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider mb-3">Alert Timeline</h3>
          <div className="max-h-[500px] overflow-y-auto space-y-1">
            {displayed.map((alert) => (
              <button
                key={alert.alert_id}
                onClick={() => setSelectedAlert(alert)}
                className={`w-full text-left flex items-start gap-3 px-3 py-3 rounded-lg transition-all ${
                  selectedAlert?.alert_id === alert.alert_id
                    ? 'bg-signal-primary/10 border border-signal-primary/30 shadow-[0_0_8px_rgba(0,229,255,0.1)]'
                    : 'hover:bg-bg-hover border border-transparent'
                }`}
              >
                <div className="mt-1"><SeverityBadge severity={alert.severity} /></div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-text-primary truncate">{alert.title}</p>
                  <p className="text-[11px] text-text-muted mt-0.5">{alert.hostname} · {formatTimestamp(alert.triggered_at)}</p>
                  <p className="text-[11px] text-text-secondary mt-1 truncate">{alert.description}</p>
                </div>
              </button>
            ))}
            {displayed.length === 0 && (
              <p className="text-sm text-text-muted text-center py-8">No alerts in this category</p>
            )}
          </div>
        </div>

        {/* Alert Investigation + Resource Correlation */}
        <div className="lg:col-span-2 space-y-4">
          {/* Investigation Details */}
          <div className="glass-panel panel-glow rounded-xl p-5 animate-fade-in">
            <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider mb-4">Alert Investigation</h3>
            {selectedAlert ? (
              <div className="space-y-4">
                <div>
                  <h4 className="text-base font-bold text-text-primary">{selectedAlert.title}</h4>
                  <div className="mt-2"><SeverityBadge severity={selectedAlert.severity} size="md" /></div>
                </div>

                <div className="space-y-2 text-xs">
                  {[
                    { label: 'Alert ID', value: selectedAlert.alert_id, mono: true },
                    { label: 'System', value: selectedAlert.hostname },
                    { label: 'Rule', value: selectedAlert.rule },
                    { label: 'Triggered', value: formatTimestamp(selectedAlert.triggered_at) },
                    ...(selectedAlert.acknowledged ? [{ label: 'Ack by', value: selectedAlert.acknowledged_by || '' }] : []),
                  ].map((f) => (
                    <div key={f.label} className="flex justify-between py-1.5 border-b border-border/30">
                      <span className="text-text-muted">{f.label}</span>
                      <span className={`text-text-secondary ${f.mono ? 'font-mono' : ''}`}>{f.value}</span>
                    </div>
                  ))}
                </div>

                <p className="text-xs text-text-secondary leading-relaxed">{selectedAlert.description}</p>

                {!selectedAlert.acknowledged && (
                  <div className="flex gap-2 pt-2">
                    <button className="flex items-center gap-1.5 px-4 py-2 bg-signal-primary hover:bg-signal-primary/80 text-black text-xs font-medium rounded-lg transition-colors shadow-[0_0_12px_rgba(0,229,255,0.2)]">
                      <Check className="w-3.5 h-3.5" /> Acknowledge
                    </button>
                    <button className="flex items-center gap-1.5 px-4 py-2 border border-border text-text-secondary hover:text-text-primary hover:bg-bg-hover text-xs font-medium rounded-lg transition-colors">
                      <ArrowUpRight className="w-3.5 h-3.5" /> Escalate
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center py-12 text-text-muted">
                <p className="text-sm">Select an alert to investigate</p>
              </div>
            )}
          </div>

          {/* Resource Correlation Chart */}
          {selectedAlert && correlationData.length > 0 && (
            <div className="glass-panel panel-glow rounded-xl p-5 animate-fade-in">
              <h5 className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-3">Resource Correlation — {selectedAlert.hostname}</h5>
              <ResponsiveContainer width="100%" height={160}>
                <ComposedChart data={correlationData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="cpuAlert" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#00e5ff" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#00e5ff" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1a2230" strokeOpacity={0.25} vertical={false} />
                  <XAxis dataKey="time" tick={{ fill: '#556171', fontSize: 9 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#556171', fontSize: 9 }} axisLine={false} tickLine={false} domain={[0, 100]} />
                  <Tooltip contentStyle={{ backgroundColor: '#05080f', border: '1px solid #1a2230', borderRadius: 8, fontSize: 11, color: '#e6edf3' }} />
                  <Area type="monotone" dataKey="cpu" stroke="#00e5ff" fill="url(#cpuAlert)" strokeWidth={1.5} name="CPU %" />
                  <Line type="monotone" dataKey="memory" stroke="#8b5cf6" strokeWidth={1.5} dot={false} name="Memory %" />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
