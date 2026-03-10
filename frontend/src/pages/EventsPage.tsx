import { useState, useMemo } from 'react';
import { ArrowUpDown } from 'lucide-react';
import SeverityBadge from '../components/shared/SeverityBadge';
import LiveEventStream from '../components/shared/LiveEventStream';
import EventDetailInspector from '../components/shared/EventDetailInspector';
import { formatTimestamp } from '../data/mockData';
import { useDashboard } from '../context/DashboardContext';
import type { Severity, TelemetryEvent } from '../types/telemetry';

const PAGE_SIZE = 12;
type SortKey = 'event_time' | 'severity' | 'system_id' | 'fault_type';
type SortDir = 'asc' | 'desc';
const severityOrder: Record<Severity, number> = { CRITICAL: 0, ERROR: 1, WARNING: 2, INFO: 3 };

export default function EventsPage() {
  const { filteredEvents } = useDashboard();
  const [page, setPage] = useState(0);
  const [sortKey, setSortKey] = useState<SortKey>('event_time');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [selectedEvent, setSelectedEvent] = useState<TelemetryEvent | null>(null);

  const sorted = useMemo(() => {
    return [...filteredEvents].sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'event_time') cmp = new Date(a.event_time).getTime() - new Date(b.event_time).getTime();
      else if (sortKey === 'severity') cmp = severityOrder[a.severity] - severityOrder[b.severity];
      else if (sortKey === 'system_id') cmp = a.system_id.localeCompare(b.system_id);
      else if (sortKey === 'fault_type') cmp = a.fault_type.localeCompare(b.fault_type);
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [filteredEvents, sortKey, sortDir]);

  const paginated = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(sorted.length / PAGE_SIZE);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('desc'); }
  };

  const SortHeader = ({ label, sortId }: { label: string; sortId: SortKey }) => (
    <th
      onClick={() => toggleSort(sortId)}
      className="text-left text-[10px] font-semibold text-text-muted uppercase tracking-wider py-3 px-3 cursor-pointer hover:text-text-secondary transition-colors select-none"
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <ArrowUpDown className={`w-3 h-3 ${sortKey === sortId ? 'text-signal-primary' : 'opacity-30'}`} />
      </span>
    </th>
  );

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-text-primary">Event Explorer</h2>
          <p className="text-xs text-text-muted mt-0.5">Investigate telemetry events</p>
        </div>
        <span className="text-xs text-text-muted glass-panel rounded-lg px-3 py-1.5">
          {filteredEvents.length} events matching
        </span>
      </div>

      {/* ── Top: Live Event Stream ── */}
      <LiveEventStream />

      {/* ── Bottom: Table + Inspector ── */}
      <div className={`grid gap-4 ${selectedEvent ? 'grid-cols-1 lg:grid-cols-5' : 'grid-cols-1'}`}>
        {/* Events Table */}
        <div className={`${selectedEvent ? 'lg:col-span-3' : ''} glass-panel panel-glow rounded-xl overflow-hidden animate-fade-in`}>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border">
                  <SortHeader label="Time" sortId="event_time" />
                  <SortHeader label="System" sortId="system_id" />
                  <th className="text-left text-[10px] font-semibold text-text-muted uppercase tracking-wider py-3 px-3">Provider</th>
                  <th className="text-left text-[10px] font-semibold text-text-muted uppercase tracking-wider py-3 px-3">ID</th>
                  <SortHeader label="Severity" sortId="severity" />
                  <SortHeader label="Fault Type" sortId="fault_type" />
                  <th className="text-left text-[10px] font-semibold text-text-muted uppercase tracking-wider py-3 px-3">Message</th>
                </tr>
              </thead>
              <tbody>
                {paginated.map((e) => (
                  <tr
                    key={e.event_record_id}
                    onClick={() => setSelectedEvent(e)}
                    className={`border-b border-border/30 transition-colors cursor-pointer ${
                      selectedEvent?.event_record_id === e.event_record_id
                        ? 'bg-signal-primary/10'
                        : 'hover:bg-bg-hover'
                    }`}
                  >
                    <td className="py-2.5 px-3 text-text-muted whitespace-nowrap font-mono">{formatTimestamp(e.event_time)}</td>
                    <td className="py-2.5 px-3">
                      <span className="font-mono text-signal-primary">{e.system_id}</span>
                      <p className="text-[10px] text-text-muted">{e.hostname}</p>
                    </td>
                    <td className="py-2.5 px-3 text-text-secondary max-w-[150px] truncate">{e.provider_name}</td>
                    <td className="py-2.5 px-3 font-mono text-text-muted">{e.event_id}</td>
                    <td className="py-2.5 px-3"><SeverityBadge severity={e.severity} /></td>
                    <td className="py-2.5 px-3 text-text-secondary">{e.fault_type}</td>
                    <td className="py-2.5 px-3 text-text-muted max-w-[240px] truncate">{e.fault_description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between px-3 py-2.5 border-t border-border">
            <p className="text-[11px] text-text-muted">
              {sorted.length > 0 ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, sorted.length)} of ${sorted.length}` : 'No events'}
            </p>
            <div className="flex gap-1.5">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-2.5 py-1 text-[11px] rounded-md border border-border text-text-secondary hover:bg-bg-hover disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >Prev</button>
              <button
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                disabled={page >= totalPages - 1}
                className="px-2.5 py-1 text-[11px] rounded-md border border-border text-text-secondary hover:bg-bg-hover disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              >Next</button>
            </div>
          </div>
        </div>

        {/* Event Detail Inspector */}
        {selectedEvent && (
          <div className="lg:col-span-2">
            <EventDetailInspector event={selectedEvent} onClose={() => setSelectedEvent(null)} />
          </div>
        )}
      </div>
    </div>
  );
}
