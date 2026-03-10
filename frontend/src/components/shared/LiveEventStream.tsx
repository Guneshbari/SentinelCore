import { useState, useEffect, useRef } from 'react';
import { Radio } from 'lucide-react';
import SeverityBadge from './SeverityBadge';
import { formatTimestamp } from '../../data/mockData';
import { useDashboard } from '../../context/DashboardContext';
import type { TelemetryEvent } from '../../types/telemetry';

const MAX_VISIBLE = 12;

export default function LiveEventStream() {
  const { filteredEvents } = useDashboard();
  const [streamEvents, setStreamEvents] = useState<TelemetryEvent[]>(filteredEvents.slice(0, 5));
  const [isLive, setIsLive] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isLive) return;
    const interval = setInterval(() => {
      setStreamEvents((prev) => {
        const nextIdx = prev.length % filteredEvents.length;
        if (filteredEvents.length === 0) return prev;
        const newEvent = {
          ...filteredEvents[nextIdx],
          event_record_id: Date.now() + Math.random(),
          event_time: new Date().toISOString(),
        };
        return [newEvent, ...prev].slice(0, MAX_VISIBLE);
      });
    }, 3000);
    return () => clearInterval(interval);
  }, [isLive, filteredEvents]);

  return (
    <div className="glass-panel panel-glow rounded-xl overflow-hidden animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-2">
          <Radio className={`w-4 h-4 ${isLive ? 'text-signal-highlight neon-green' : 'text-text-muted'}`} />
          <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider">Live Event Stream</h3>
          {isLive && (
            <span className="flex items-center gap-1 text-[10px] text-signal-highlight font-medium">
              <span className="w-1.5 h-1.5 rounded-full bg-signal-highlight animate-pulse-glow" />
              LIVE
            </span>
          )}
        </div>
        <button
          onClick={() => setIsLive(!isLive)}
          className={`px-2.5 py-1 text-[10px] font-semibold rounded-md transition-colors ${
            isLive
              ? 'bg-accent-red/15 text-accent-red hover:bg-accent-red/25'
              : 'bg-signal-highlight/15 text-signal-highlight hover:bg-signal-highlight/25'
          }`}
        >
          {isLive ? 'PAUSE' : 'RESUME'}
        </button>
      </div>

      {/* Stream */}
      <div ref={containerRef} className="max-h-[280px] overflow-y-auto">
        {streamEvents.map((e, i) => (
          <div
            key={`${e.event_record_id}-${i}`}
            className={`flex items-center gap-3 px-4 py-2 border-b border-border/30 text-xs hover:bg-bg-hover transition-colors cursor-pointer ${
              i === 0 ? 'animate-slide-in bg-bg-hover/50' : ''
            }`}
          >
            <span className="text-text-muted font-mono whitespace-nowrap w-[110px] shrink-0">
              {formatTimestamp(e.event_time)}
            </span>
            <span className="font-mono text-signal-primary w-[65px] shrink-0">{e.system_id}</span>
            <span className="w-[70px] shrink-0">
              <SeverityBadge severity={e.severity} />
            </span>
            <span className="text-text-secondary w-[100px] shrink-0 truncate">{e.fault_type}</span>
            <span className="text-text-muted truncate flex-1">{e.fault_description}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
