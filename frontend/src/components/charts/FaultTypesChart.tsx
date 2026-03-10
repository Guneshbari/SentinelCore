import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { getTopFaultTypes } from '../../data/mockData';

export default function FaultTypesChart() {
  const data = getTopFaultTypes();

  return (
    <div className="glass-panel rounded-xl p-5 animate-fade-in">
      <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider mb-1">Top Fault Types</h3>
      <p className="text-[10px] text-text-muted mb-4">Most common fault categories</p>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="barGrad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#0a84ff" />
              <stop offset="100%" stopColor="#bf5af2" />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" horizontal={false} />
          <XAxis type="number" tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={{ stroke: '#1f2937' }} tickLine={false} />
          <YAxis type="category" dataKey="fault_type" tick={{ fill: '#6b7280', fontSize: 10 }} axisLine={false} tickLine={false} width={110} />
          <Tooltip contentStyle={{ backgroundColor: '#0b0f19', border: '1px solid #1f2937', borderRadius: 8, fontSize: 11, color: '#e5e7eb' }} />
          <Bar dataKey="count" fill="url(#barGrad)" radius={[0, 4, 4, 0]} barSize={20} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
