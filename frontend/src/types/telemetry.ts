export type Severity = 'CRITICAL' | 'ERROR' | 'WARNING' | 'INFO';

export interface TelemetryEvent {
  system_id: string;
  hostname: string;
  event_record_id: number;
  provider_name: string;
  event_id: number;
  severity: Severity;
  fault_type: string;
  fault_description: string;
  cpu_usage_percent: number;
  memory_usage_percent: number;
  disk_free_percent: number;
  event_time: string;
  created_at: string;
  log_channel: string;
}

export type SystemStatus = 'online' | 'degraded' | 'offline';

export interface SystemInfo {
  system_id: string;
  hostname: string;
  status: SystemStatus;
  cpu_usage_percent: number;
  memory_usage_percent: number;
  disk_free_percent: number;
  os_version: string;
  last_seen: string;
  ip_address: string;
  total_events: number;
}

export interface Alert {
  alert_id: string;
  system_id: string;
  hostname: string;
  severity: Severity;
  rule: string;
  title: string;
  description: string;
  triggered_at: string;
  acknowledged: boolean;
  acknowledged_at?: string;
  acknowledged_by?: string;
}

export interface MetricPoint {
  timestamp: string;
  event_count: number;
  critical_count: number;
  error_count: number;
  warning_count: number;
  info_count: number;
  avg_cpu: number;
  avg_memory: number;
  avg_disk_free: number;
}

export interface SeverityCount {
  severity: Severity;
  count: number;
}

export interface FaultTypeCount {
  fault_type: string;
  count: number;
}

export interface SystemFailureCount {
  hostname: string;
  system_id: string;
  failure_count: number;
}
