import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from 'react';
import type { Severity, TelemetryEvent } from '../types/telemetry';
import { events as allEvents } from '../data/mockData';

// ── Types ───────────────────────────────────────────────
export type TimeRange = '5m' | '15m' | '1h' | '6h' | '24h';
export type AutoRefresh = 'off' | '5s' | '10s' | '30s' | '1m';

const TIME_RANGE_MS: Record<TimeRange, number> = {
  '5m': 5 * 60_000,
  '15m': 15 * 60_000,
  '1h': 60 * 60_000,
  '6h': 6 * 60 * 60_000,
  '24h': 24 * 60 * 60_000,
};

const REFRESH_MS: Record<AutoRefresh, number | null> = {
  off: null,
  '5s': 5_000,
  '10s': 10_000,
  '30s': 30_000,
  '1m': 60_000,
};

export const TIME_RANGE_LABELS: Record<TimeRange, string> = {
  '5m': 'Last 5 min',
  '15m': 'Last 15 min',
  '1h': 'Last 1 hour',
  '6h': 'Last 6 hours',
  '24h': 'Last 24 hours',
};

export const REFRESH_LABELS: Record<AutoRefresh, string> = {
  off: 'Off',
  '5s': '5s',
  '10s': '10s',
  '30s': '30s',
  '1m': '1m',
};

interface DashboardState {
  // Time range
  timeRange: TimeRange;
  setTimeRange: (r: TimeRange) => void;
  autoRefresh: AutoRefresh;
  setAutoRefresh: (r: AutoRefresh) => void;

  // Global filters
  selectedSystems: string[];
  setSelectedSystems: (s: string[]) => void;
  selectedSeverities: Severity[];
  setSelectedSeverities: (s: Severity[]) => void;
  selectedFaultTypes: string[];
  setSelectedFaultTypes: (f: string[]) => void;
  searchQuery: string;
  setSearchQuery: (q: string) => void;

  // Computed
  filteredEvents: TelemetryEvent[];
  refreshTick: number;
  clearFilters: () => void;
  hasActiveFilters: boolean;
}

const DashboardContext = createContext<DashboardState | null>(null);

// ── Provider ─────────────────────────────────────────────
interface DashboardProviderProps {
  readonly children: ReactNode;
}

export function DashboardProvider({ children }: DashboardProviderProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>('15m');
  const [autoRefresh, setAutoRefresh] = useState<AutoRefresh>('off');
  const [selectedSystems, setSelectedSystems] = useState<string[]>([]);
  const [selectedSeverities, setSelectedSeverities] = useState<Severity[]>([]);
  const [selectedFaultTypes, setSelectedFaultTypes] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [refreshTick, setRefreshTick] = useState(0);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Auto-refresh timer
  useEffect(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    const ms = REFRESH_MS[autoRefresh];
    if (ms) {
      intervalRef.current = setInterval(() => setRefreshTick((t) => t + 1), ms);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [autoRefresh]);

  const clearFilters = useCallback(() => {
    setSelectedSystems([]);
    setSelectedSeverities([]);
    setSelectedFaultTypes([]);
    setSearchQuery('');
  }, []);

  const hasActiveFilters =
    selectedSystems.length > 0 ||
    selectedSeverities.length > 0 ||
    selectedFaultTypes.length > 0 ||
    searchQuery.length > 0;

  // Filter events based on all global state
  const filteredEvents = allEvents.filter((e) => {
    // Time range filter — use mock reference time
    const refTime = new Date('2026-03-08T14:25:00Z').getTime();
    const eventTime = new Date(e.event_time).getTime();
    if (eventTime < refTime - TIME_RANGE_MS[timeRange]) return false;

    // System filter
    if (selectedSystems.length > 0 && !selectedSystems.includes(e.hostname)) return false;

    // Severity filter
    if (selectedSeverities.length > 0 && !selectedSeverities.includes(e.severity)) return false;

    // Fault type filter
    if (selectedFaultTypes.length > 0 && !selectedFaultTypes.includes(e.fault_type)) return false;

    // Search
    if (searchQuery) {
      const term = searchQuery.toLowerCase();
      const matches =
        e.fault_description.toLowerCase().includes(term) ||
        e.system_id.toLowerCase().includes(term) ||
        e.fault_type.toLowerCase().includes(term) ||
        e.provider_name.toLowerCase().includes(term) ||
        String(e.event_id).includes(term);
      if (!matches) return false;
    }

    return true;
  });

  return (
    <DashboardContext.Provider
      value={{
        timeRange,
        setTimeRange,
        autoRefresh,
        setAutoRefresh,
        selectedSystems,
        setSelectedSystems,
        selectedSeverities,
        setSelectedSeverities,
        selectedFaultTypes,
        setSelectedFaultTypes,
        searchQuery,
        setSearchQuery,
        filteredEvents,
        refreshTick,
        clearFilters,
        hasActiveFilters,
      }}
    >
      {children}
    </DashboardContext.Provider>
  );
}

// ── Hook ─────────────────────────────────────────────────
export function useDashboard(): DashboardState {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error('useDashboard must be used within DashboardProvider');
  return ctx;
}
