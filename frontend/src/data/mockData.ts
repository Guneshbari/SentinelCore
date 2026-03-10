import type {
  TelemetryEvent,
  SystemInfo,
  Alert,
  MetricPoint,
  Severity,
  SeverityCount,
  FaultTypeCount,
  SystemFailureCount,
} from '../types/telemetry';

import eventsData from '../../mock-data/events.json';
import systemsData from '../../mock-data/systems.json';
import alertsData from '../../mock-data/alerts.json';
import metricsData from '../../mock-data/metrics.json';

// ── Raw data exports ───────────────────────────────────
export const events: TelemetryEvent[] = eventsData.data as TelemetryEvent[];
export const systems: SystemInfo[] = systemsData.data as SystemInfo[];
export const alerts: Alert[] = alertsData.data as Alert[];
export const metrics: MetricPoint[] = metricsData.data as MetricPoint[];

// ── Helper functions ───────────────────────────────────
// These can be replaced with API calls in the future

export function getEventsBySeverity(severity: Severity): TelemetryEvent[] {
  return events.filter((e) => e.severity === severity);
}

export function getSystemById(id: string): SystemInfo | undefined {
  return systems.find((s) => s.system_id === id);
}

export function getActiveAlerts(): Alert[] {
  return alerts.filter((a) => !a.acknowledged);
}

export function getAcknowledgedAlerts(): Alert[] {
  return alerts.filter((a) => a.acknowledged);
}

export function getAlertsBySeverity(severity: Severity): Alert[] {
  return alerts.filter((a) => a.severity === severity);
}

export function getSeverityDistribution(): SeverityCount[] {
  const counts: Record<Severity, number> = { CRITICAL: 0, ERROR: 0, WARNING: 0, INFO: 0 };
  events.forEach((e) => counts[e.severity]++);
  return Object.entries(counts).map(([severity, count]) => ({
    severity: severity as Severity,
    count,
  }));
}

export function getTopFaultTypes(limit = 5): FaultTypeCount[] {
  const counts: Record<string, number> = {};
  events.forEach((e) => {
    counts[e.fault_type] = (counts[e.fault_type] || 0) + 1;
  });
  return Object.entries(counts)
    .map(([fault_type, count]) => ({ fault_type, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, limit);
}

export function getTopFailingSystems(limit = 5): SystemFailureCount[] {
  const counts: Record<string, { hostname: string; count: number }> = {};
  events
    .filter((e) => e.severity === 'CRITICAL' || e.severity === 'ERROR')
    .forEach((e) => {
      if (!counts[e.system_id]) {
        counts[e.system_id] = { hostname: e.hostname, count: 0 };
      }
      counts[e.system_id].count++;
    });
  return Object.entries(counts)
    .map(([system_id, { hostname, count }]) => ({
      system_id,
      hostname,
      failure_count: count,
    }))
    .sort((a, b) => b.failure_count - a.failure_count)
    .slice(0, limit);
}

export function getOnlineSystems(): number {
  return systems.filter((s) => s.status === 'online').length;
}

export function getDegradedSystems(): number {
  return systems.filter((s) => s.status === 'degraded').length;
}

export function getOfflineSystems(): number {
  return systems.filter((s) => s.status === 'offline').length;
}

export function getTotalEventCount(): number {
  return events.length;
}

export function getCriticalAlertCount(): number {
  return getActiveAlerts().filter((a) => a.severity === 'CRITICAL').length;
}

export function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

export function formatTimeShort(ts: string): string {
  const d = new Date(ts);
  return d.toLocaleString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export function timeAgo(ts: string): string {
  const now = new Date('2026-03-08T14:25:00Z'); // fixed reference for mock
  const then = new Date(ts);
  const diffMs = now.getTime() - then.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${Math.floor(diffHr / 24)}d ago`;
}
