import { useState, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Search, X, ArrowUpDown } from 'lucide-react';
import SeverityBadge from '../components/shared/SeverityBadge';
import LiveEventStream from '../components/shared/LiveEventStream';
import EventDetailInspector from '../components/shared/EventDetailInspector';
import { events, formatTimestamp } from '../data/mockData';
import type { Severity, TelemetryEvent } from '../types/telemetry';

const SEVERITIES: Severity[] = ['CRITICAL', 'ERROR', 'WARNING', 'INFO'];
const PAGE_SIZE = 10;

type SortKey = 'event_time' | 'severity' | 'system_id' | 'fault_type';
type SortDir = 'asc' | 'desc';

const severityOrder: Record<Severity, number> = { CRITICAL: 0, ERROR: 1, WARNING: 2, INFO: 3 };

export default function EventsPage() {
  const [searchParams] = useSearchParams();
  const systemFromURL = searchParams.get('system') || 'ALL';

  const [searchTerm, setSearchTerm] = useState('');
  const [severityFilter, setSeverityFilter] = useState<Severity | 'ALL'>('ALL');
  const [systemFilter, setSystemFilter] = useState<string>(systemFromURL);
  const [faultTypeFilter, setFaultTypeFilter] = useState<string>('ALL');
  const [page, setPage] = useState(0);
  const [sortKey, setSortKey] = useState<SortKey>('event_time');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [selectedEvent, setSelectedEvent] = useState<TelemetryEvent | null>(null);

  const uniqueSystems = useMemo(() => [...new Set(events.map((e) => e.hostname))].sort(), []);
  const uniqueFaultTypes = useMemo(() => [...new Set(events.map((e) => e.fault_type))].sort(), []);

  const filtered = useMemo(() => {
    let result = events.filter((e) => {
      if (severityFilter !== 'ALL' && e.severity !== severityFilter) return false;
      if (systemFilter !== 'ALL' && e.hostname !== systemFilter) return false;
      if (faultTypeFilter !== 'ALL' && e.fault_type !== faultTypeFilter) return false;
      if (searchTerm) {
        const term = searchTerm.toLowerCase();
        return (
          e.fault_description.toLowerCase().includes(term) ||
          e.system_id.toLowerCase().includes(term) ||
          e.fault_type.toLowerCase().includes(term) ||
          e.provider_name.toLowerCase().includes(term)
        );
      }
      return true;
    });

    // Sort
    result = [...result].sort((a, b) => {
      let cmp = 0;
      if (sortKey === 'event_time') cmp = new Date(a.event_time).getTime() - new Date(b.event_time).getTime();
      else if (sortKey === 'severity') cmp = severityOrder[a.severity] - severityOrder[b.severity];
      else if (sortKey === 'system_id') cmp = a.system_id.localeCompare(b.system_id);
      else if (sortKey === 'fault_type') cmp = a.fault_type.localeCompare(b.fault_type);
      return sortDir === 'asc' ? cmp : -cmp;
    });

    return result;
  }, [searchTerm, severityFilter, systemFilter, faultTypeFilter, sortKey, sortDir]);

  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortKey(key); setSortDir('desc'); }
  };

  const clearFilters = () => {
    setSearchTerm('');
    setSeverityFilter('ALL');
    setSystemFilter('ALL');
    setFaultTypeFilter('ALL');
    setPage(0);
  };

  const SortHeader = ({ label, sortId }: { label: string; sortId: SortKey }) => (
    <th
      onClick={() => toggleSort(sortId)}
      className="text-left text-[10px] font-semibold text-text-muted uppercase tracking-wider py-3 px-3 cursor-pointer hover:text-text-secondary transition-colors select-none"
    >
      <span className="inline-flex items-center gap-1">
        {label}
        <ArrowUpDown className={`w-3 h-3 ${sortKey === sortId ? 'text-accent-blue' : 'opacity-30'}`} />
      </span>
    </th>
  );

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <h2 className="text-lg font-bold text-text-primary">Event Explorer</h2>
        <p className="text-xs text-text-muted mt-0.5">Investigate telemetry events</p>
      </div>

      {/* Live Event Stream */}
      <LiveEventStream />

      {/* Filter Bar */}
      <div className="glass-panel rounded-xl p-3 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
          <input
            type="text"
            placeholder="Search events..."
            value={searchTerm}
            onChange={(e) => { setSearchTerm(e.target.value); setPage(0); }}
            className="w-full bg-bg-primary/50 border border-border rounded-lg py-1.5 pl-9 pr-4 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-blue/50 transition-all"
          />
        </div>

        <select
          value={severityFilter}
          onChange={(e) => { setSeverityFilter(e.target.value as Severity | 'ALL'); setPage(0); }}
          className="bg-bg-primary/50 border border-border rounded-lg py-1.5 px-2.5 text-xs text-text-primary focus:outline-none focus:border-accent-blue/50 cursor-pointer"
        >
          <option value="ALL">All Severities</option>
          {SEVERITIES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>

        <select
          value={systemFilter}
          onChange={(e) => { setSystemFilter(e.target.value); setPage(0); }}
          className="bg-bg-primary/50 border border-border rounded-lg py-1.5 px-2.5 text-xs text-text-primary focus:outline-none focus:border-accent-blue/50 cursor-pointer"
        >
          <option value="ALL">All Systems</option>
          {uniqueSystems.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>

        <select
          value={faultTypeFilter}
          onChange={(e) => { setFaultTypeFilter(e.target.value); setPage(0); }}
          className="bg-bg-primary/50 border border-border rounded-lg py-1.5 px-2.5 text-xs text-text-primary focus:outline-none focus:border-accent-blue/50 cursor-pointer"
        >
          <option value="ALL">All Fault Types</option>
          {uniqueFaultTypes.map((ft) => <option key={ft} value={ft}>{ft}</option>)}
        </select>

        {(searchTerm || severityFilter !== 'ALL' || systemFilter !== 'ALL' || faultTypeFilter !== 'ALL') && (
          <button onClick={clearFilters} className="flex items-center gap-1 text-[11px] text-accent-blue hover:text-accent-blue-hover transition-colors">
            <X className="w-3 h-3" /> Clear
          </button>
        )}
      </div>

      {/* Main Content: Table + Inspector */}
      <div className={`grid gap-4 ${selectedEvent ? 'grid-cols-1 lg:grid-cols-5' : 'grid-cols-1'}`}>
        {/* Events Table */}
        <div className={`${selectedEvent ? 'lg:col-span-3' : ''} glass-panel rounded-xl overflow-hidden animate-fade-in`}>
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
                        ? 'bg-accent-blue/10'
                        : 'hover:bg-bg-hover'
                    }`}
                  >
                    <td className="py-2.5 px-3 text-text-muted whitespace-nowrap font-mono">{formatTimestamp(e.event_time)}</td>
                    <td className="py-2.5 px-3">
                      <span className="font-mono text-accent-blue">{e.system_id}</span>
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
              {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
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
