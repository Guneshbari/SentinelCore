import { Search, Bell, Activity, Server, AlertTriangle, Zap } from 'lucide-react';
import {
  getOnlineSystems,
  getDegradedSystems,
  getOfflineSystems,
  getCriticalAlertCount,
  getTotalEventCount,
  systems,
} from '../../data/mockData';

export default function Topbar() {
  const online = getOnlineSystems();
  const degraded = getDegradedSystems();
  const offline = getOfflineSystems();
  const criticals = getCriticalAlertCount();
  const totalEvents = getTotalEventCount();

  return (
    <header className="fixed top-0 left-[220px] right-0 h-[56px] bg-bg-surface/70 backdrop-blur-xl border-b border-border flex items-center justify-between px-5 z-40">
      {/* Status Summary Strip */}
      <div className="flex items-center gap-4">
        {/* Systems Online */}
        <div className="flex items-center gap-1.5">
          <Server className="w-3.5 h-3.5 text-accent-green" />
          <span className="text-xs font-semibold text-accent-green">{online}</span>
          <span className="text-[10px] text-text-muted">online</span>
        </div>

        <span className="w-px h-4 bg-border" />

        {/* Degraded */}
        <div className="flex items-center gap-1.5">
          <Activity className="w-3.5 h-3.5 text-accent-amber" />
          <span className="text-xs font-semibold text-accent-amber">{degraded}</span>
          <span className="text-[10px] text-text-muted">degraded</span>
        </div>

        <span className="w-px h-4 bg-border" />

        {/* Critical Alerts */}
        <div className="flex items-center gap-1.5">
          <AlertTriangle className={`w-3.5 h-3.5 ${criticals > 0 ? 'text-accent-red neon-red' : 'text-text-muted'}`} />
          <span className={`text-xs font-semibold ${criticals > 0 ? 'text-accent-red' : 'text-text-muted'}`}>{criticals}</span>
          <span className="text-[10px] text-text-muted">critical</span>
        </div>

        <span className="w-px h-4 bg-border" />

        {/* Events / hr */}
        <div className="flex items-center gap-1.5">
          <Zap className="w-3.5 h-3.5 text-accent-blue" />
          <span className="text-xs font-semibold text-accent-blue">{totalEvents}</span>
          <span className="text-[10px] text-text-muted">events</span>
        </div>

        <span className="w-px h-4 bg-border" />

        {/* Pipeline health */}
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-accent-green shadow-[0_0_6px_rgba(52,199,89,0.5)]" />
          <span className="text-[10px] text-text-muted">Pipeline OK</span>
        </div>
      </div>

      {/* Search */}
      <div className="flex-1 max-w-sm mx-6">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
          <input
            type="text"
            placeholder="Search events, systems, alerts..."
            className="w-full bg-bg-primary/50 border border-border rounded-lg py-1.5 pl-9 pr-4 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-blue/50 focus:shadow-[0_0_12px_rgba(10,132,255,0.1)] transition-all"
          />
        </div>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-3">
        <button className="relative p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors">
          <Bell className="w-4 h-4" />
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-accent-red rounded-full flex items-center justify-center text-[9px] font-bold text-white shadow-[0_0_8px_rgba(255,59,48,0.4)]">
            {criticals + degraded}
          </span>
        </button>
        <div className="w-7 h-7 rounded-full bg-accent-blue/20 flex items-center justify-center text-[10px] font-semibold text-accent-blue border border-accent-blue/30">
          GS
        </div>
      </div>
    </header>
  );
}
