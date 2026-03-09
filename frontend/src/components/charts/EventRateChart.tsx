import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { metrics, formatTimeShort } from '../../data/mockData';

export default function EventRateChart() {
  const data = metrics.map((m) => ({
    time: formatTimeShort(m.timestamp),
    events: m.event_count,
  }));

  return (
    <div className="glass-panel rounded-xl p-5 animate-fade-in">
      <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider mb-1">Event Rate</h3>
      <p className="text-[10px] text-text-muted mb-4">Events per hour over the last 15 hours</p>
      <div className="neon-blue">
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={data} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="eventGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#0a84ff" stopOpacity={0.3} />
                <stop offset="100%" stopColor="#0a84ff" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" vertical={false} />
            <XAxis dataKey="time" tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={{ stroke: '#1f2937' }} tickLine={false} />
            <YAxis tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={false} tickLine={false} />
            <Tooltip contentStyle={{ backgroundColor: '#0b0f19', border: '1px solid #1f2937', borderRadius: 8, fontSize: 11, color: '#e5e7eb' }} />
            <Area type="monotone" dataKey="events" stroke="#0a84ff" strokeWidth={2} fill="url(#eventGrad)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
