import {
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { metrics, formatTimeShort, getTopFaultTypes, getTopFailingSystems } from '../data/mockData';

const FAULT_COLORS = ['#0a84ff', '#34c759', '#ffd60a', '#ff3b30', '#64d2ff', '#bf5af2'];

export default function AnalyticsPage() {
  const freqData = metrics.map((m) => ({
    time: formatTimeShort(m.timestamp),
    Total: m.event_count,
    Errors: m.error_count,
    Warnings: m.warning_count,
    Critical: m.critical_count,
  }));

  const failingSystems = getTopFailingSystems();
  const faultTypes = getTopFaultTypes(6);

  const scatterData = metrics.map((m) => ({
    cpu: m.avg_cpu,
    memory: m.avg_memory,
    events: m.event_count,
  }));

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-text-primary">Analytics</h2>
          <p className="text-xs text-text-muted mt-0.5">Analyze telemetry trends & patterns</p>
        </div>
        <span className="px-3 py-1.5 rounded-lg glass-panel text-xs text-text-secondary">Last 15 Hours</span>
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Event Frequency */}
        <div className="glass-panel rounded-xl p-5 animate-fade-in">
          <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider mb-1">Event Frequency Timeline</h3>
          <p className="text-[10px] text-text-muted mb-4">Event counts by severity over time</p>
          <div className="neon-blue">
            <ResponsiveContainer width="100%" height={260}>
              <LineChart data={freqData} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
                <XAxis dataKey="time" tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={{ stroke: '#1f2937' }} tickLine={false} />
                <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={false} tickLine={false} />
                <Tooltip contentStyle={{ backgroundColor: '#0b0f19', border: '1px solid #1f2937', borderRadius: 8, fontSize: 11, color: '#e5e7eb' }} />
                <Legend verticalAlign="bottom" height={36} formatter={(v: string) => <span className="text-[10px] text-text-secondary">{v}</span>} />
                <Line type="monotone" dataKey="Total" stroke="#0a84ff" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="Errors" stroke="#ff9500" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
                <Line type="monotone" dataKey="Warnings" stroke="#ffd60a" strokeWidth={1.5} dot={false} strokeDasharray="4 2" />
                <Line type="monotone" dataKey="Critical" stroke="#ff3b30" strokeWidth={1.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Top Failing Systems */}
        <div className="glass-panel rounded-xl p-5 animate-fade-in">
          <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider mb-1">Top Failing Systems</h3>
          <p className="text-[10px] text-text-muted mb-4">Ranked by critical + error events</p>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={failingSystems} layout="vertical" margin={{ top: 0, right: 10, left: 10, bottom: 0 }}>
              <defs>
                <linearGradient id="failGrad" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#0a84ff" />
                  <stop offset="100%" stopColor="#bf5af2" />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" horizontal={false} />
              <XAxis type="number" tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={{ stroke: '#1f2937' }} tickLine={false} />
              <YAxis type="category" dataKey="hostname" tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={false} tickLine={false} width={120} />
              <Tooltip contentStyle={{ backgroundColor: '#0b0f19', border: '1px solid #1f2937', borderRadius: 8, fontSize: 11, color: '#e5e7eb' }} />
              <Bar dataKey="failure_count" fill="url(#failGrad)" radius={[0, 4, 4, 0]} barSize={22} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Fault Type Distribution */}
        <div className="glass-panel rounded-xl p-5 animate-fade-in">
          <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider mb-1">Fault Type Distribution</h3>
          <p className="text-[10px] text-text-muted mb-4">Event breakdown by fault category</p>
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={faultTypes} dataKey="count" nameKey="fault_type" cx="50%" cy="50%" innerRadius={50} outerRadius={90} strokeWidth={2} stroke="#000000">
                {faultTypes.map((_, i) => <Cell key={i} fill={FAULT_COLORS[i % FAULT_COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={{ backgroundColor: '#0b0f19', border: '1px solid #1f2937', borderRadius: 8, fontSize: 11, color: '#e5e7eb' }} />
              <Legend verticalAlign="bottom" height={36} formatter={(v: string) => <span className="text-[10px] text-text-secondary">{v}</span>} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Resource Correlations */}
        <div className="glass-panel rounded-xl p-5 animate-fade-in">
          <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider mb-1">Resource Correlations</h3>
          <p className="text-[10px] text-text-muted mb-4">CPU vs Memory — color by event volume</p>
          <ResponsiveContainer width="100%" height={260}>
            <ScatterChart margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis type="number" dataKey="cpu" name="CPU %" tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={{ stroke: '#1f2937' }} tickLine={false} domain={[0, 100]} />
              <YAxis type="number" dataKey="memory" name="Memory %" tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={false} tickLine={false} domain={[0, 100]} />
              <Tooltip contentStyle={{ backgroundColor: '#0b0f19', border: '1px solid #1f2937', borderRadius: 8, fontSize: 11, color: '#e5e7eb' }} />
              <Scatter data={scatterData} fill="#0a84ff">
                {scatterData.map((entry, i) => (
                  <Cell key={i} fill={entry.events > 100 ? '#ff3b30' : entry.events > 50 ? '#ffd60a' : '#34c759'} />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
