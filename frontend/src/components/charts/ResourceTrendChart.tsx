import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { metrics, formatTimeShort } from '../../data/mockData';

export default function ResourceTrendChart() {
  const data = metrics.map((m) => ({
    time: formatTimeShort(m.timestamp),
    CPU: m.avg_cpu,
    Memory: m.avg_memory,
    'Disk Free': m.avg_disk_free,
  }));

  return (
    <div className="glass-panel panel-glow hover-lift rounded-xl p-5 animate-fade-in">
      <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider mb-1">Resource Usage Trends</h3>
      <p className="text-[10px] text-text-muted mb-4">Average CPU, memory, and disk utilization</p>
      <div className="neon-cyan">
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1a2230" strokeOpacity={0.25} vertical={false} />
            <XAxis dataKey="time" tick={{ fill: '#556171', fontSize: 10 }} axisLine={{ stroke: '#1a2230' }} tickLine={false} />
            <YAxis tick={{ fill: '#556171', fontSize: 10 }} axisLine={false} tickLine={false} domain={[0, 100]} />
            <Tooltip contentStyle={{ backgroundColor: '#05080f', border: '1px solid #1a2230', borderRadius: 8, fontSize: 11, color: '#e6edf3' }} />
            <Legend verticalAlign="bottom" height={36} formatter={(v: string) => <span className="text-[10px] text-text-secondary">{v}</span>} />
            <Line type="monotone" dataKey="CPU" stroke="#00e5ff" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="Memory" stroke="#8b5cf6" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="Disk Free" stroke="#22c55e" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
