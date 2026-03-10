import { X, Search, Filter, ChevronDown } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { useDashboard } from '../../context/DashboardContext';
import { events } from '../../data/mockData';
import type { Severity } from '../../types/telemetry';

const ALL_SEVERITIES: Severity[] = ['CRITICAL', 'ERROR', 'WARNING', 'INFO'];
const ALL_FAULT_TYPES = [...new Set(events.map((e) => e.fault_type))].sort();
const ALL_SYSTEMS = [...new Set(events.map((e) => e.hostname))].sort();

const SEVERITY_COLORS: Record<Severity, string> = {
  CRITICAL: '#ff3b30',
  ERROR: '#ff7a18',
  WARNING: '#ffd60a',
  INFO: '#00c2ff',
};

export default function GlobalFilterBar() {
  const {
    selectedSystems, setSelectedSystems,
    selectedSeverities, setSelectedSeverities,
    selectedFaultTypes, setSelectedFaultTypes,
    searchQuery, setSearchQuery,
    clearFilters, hasActiveFilters,
  } = useDashboard();

  const [showSystems, setShowSystems] = useState(false);
  const [showFaults, setShowFaults] = useState(false);
  const sysRef = useRef<HTMLDivElement>(null);
  const faultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (sysRef.current && !sysRef.current.contains(e.target as Node)) setShowSystems(false);
      if (faultRef.current && !faultRef.current.contains(e.target as Node)) setShowFaults(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const toggleSeverity = (s: Severity) => {
    setSelectedSeverities(
      selectedSeverities.includes(s)
        ? selectedSeverities.filter((x) => x !== s)
        : [...selectedSeverities, s]
    );
  };

  const toggleSystem = (sys: string) => {
    setSelectedSystems(
      selectedSystems.includes(sys)
        ? selectedSystems.filter((x) => x !== sys)
        : [...selectedSystems, sys]
    );
  };

  const toggleFault = (ft: string) => {
    setSelectedFaultTypes(
      selectedFaultTypes.includes(ft)
        ? selectedFaultTypes.filter((x) => x !== ft)
        : [...selectedFaultTypes, ft]
    );
  };

  return (
    <div className="fixed top-[56px] left-[220px] right-0 h-[40px] bg-bg-surface/50 backdrop-blur-xl border-b border-border/50 flex items-center gap-3 px-5 z-30">
      {/* Filter icon */}
      <Filter className="w-3.5 h-3.5 text-text-muted shrink-0" />

      {/* Severity Pills */}
      <div className="flex items-center gap-1">
        {ALL_SEVERITIES.map((s) => (
          <button
            key={s}
            onClick={() => toggleSeverity(s)}
            className={`flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-semibold transition-all ${
              selectedSeverities.includes(s)
                ? 'bg-opacity-20 border'
                : 'text-text-muted hover:text-text-secondary'
            }`}
            style={
              selectedSeverities.includes(s)
                ? {
                    backgroundColor: `${SEVERITY_COLORS[s]}15`,
                    borderColor: `${SEVERITY_COLORS[s]}40`,
                    color: SEVERITY_COLORS[s],
                  }
                : {}
            }
          >
            <span
              className="w-1.5 h-1.5 rounded-full"
              style={{ backgroundColor: SEVERITY_COLORS[s] }}
            />
            {s}
          </button>
        ))}
      </div>

      <span className="w-px h-5 bg-border shrink-0" />

      {/* System Multi-Select */}
      <div ref={sysRef} className="relative">
        <button
          onClick={() => { setShowSystems(!showSystems); setShowFaults(false); }}
          className={`flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium transition-all ${
            selectedSystems.length > 0
              ? 'bg-signal-primary/10 text-signal-primary border border-signal-primary/30'
              : 'text-text-muted hover:text-text-secondary'
          }`}
        >
          System{selectedSystems.length > 0 ? ` (${selectedSystems.length})` : ''}
          <ChevronDown className="w-3 h-3 opacity-50" />
        </button>
        {showSystems && (
          <div className="absolute left-0 top-full mt-1 w-48 glass-panel rounded-lg py-1 shadow-xl shadow-black/40 z-50 max-h-52 overflow-y-auto animate-fade-in">
            {ALL_SYSTEMS.map((sys) => (
              <button
                key={sys}
                onClick={() => toggleSystem(sys)}
                className={`w-full text-left px-3 py-1.5 text-[11px] transition-colors flex items-center gap-2 ${
                  selectedSystems.includes(sys)
                    ? 'text-signal-primary bg-signal-primary/10'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-hover'
                }`}
              >
                <span className={`w-3 h-3 rounded border ${
                  selectedSystems.includes(sys)
                    ? 'bg-signal-primary border-signal-primary'
                    : 'border-border'
                } flex items-center justify-center`}>
                  {selectedSystems.includes(sys) && <span className="text-[8px] text-black">✓</span>}
                </span>
                {sys}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Fault Type Selector */}
      <div ref={faultRef} className="relative">
        <button
          onClick={() => { setShowFaults(!showFaults); setShowSystems(false); }}
          className={`flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium transition-all ${
            selectedFaultTypes.length > 0
              ? 'bg-signal-secondary/10 text-signal-secondary border border-signal-secondary/30'
              : 'text-text-muted hover:text-text-secondary'
          }`}
        >
          Fault{selectedFaultTypes.length > 0 ? ` (${selectedFaultTypes.length})` : ''}
          <ChevronDown className="w-3 h-3 opacity-50" />
        </button>
        {showFaults && (
          <div className="absolute left-0 top-full mt-1 w-44 glass-panel rounded-lg py-1 shadow-xl shadow-black/40 z-50 max-h-52 overflow-y-auto animate-fade-in">
            {ALL_FAULT_TYPES.map((ft) => (
              <button
                key={ft}
                onClick={() => toggleFault(ft)}
                className={`w-full text-left px-3 py-1.5 text-[11px] transition-colors flex items-center gap-2 ${
                  selectedFaultTypes.includes(ft)
                    ? 'text-signal-secondary bg-signal-secondary/10'
                    : 'text-text-secondary hover:text-text-primary hover:bg-bg-hover'
                }`}
              >
                <span className={`w-3 h-3 rounded border ${
                  selectedFaultTypes.includes(ft)
                    ? 'bg-signal-secondary border-signal-secondary'
                    : 'border-border'
                } flex items-center justify-center`}>
                  {selectedFaultTypes.includes(ft) && <span className="text-[8px] text-white">✓</span>}
                </span>
                {ft}
              </button>
            ))}
          </div>
        )}
      </div>

      <span className="w-px h-5 bg-border shrink-0" />

      {/* Search */}
      <div className="relative flex-1 max-w-xs">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-text-muted" />
        <input
          type="text"
          placeholder="Search events..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full bg-bg-primary/30 border border-border rounded-md py-1 pl-7 pr-3 text-[11px] text-text-primary placeholder:text-text-muted focus:outline-none focus:border-signal-primary/40 transition-all"
        />
      </div>

      {/* Clear */}
      {hasActiveFilters && (
        <button
          onClick={clearFilters}
          className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium text-signal-primary hover:text-signal-primary/80 transition-colors"
        >
          <X className="w-3 h-3" />
          Clear
        </button>
      )}
    </div>
  );
}
