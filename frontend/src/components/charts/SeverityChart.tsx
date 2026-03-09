import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip,
  Legend,
} from 'recharts';
import { getSeverityDistribution } from '../../data/mockData';
import type { Severity } from '../../types/telemetry';

const COLORS: Record<Severity, string> = {
  CRITICAL: '#ff3b30',
  ERROR: '#ff9500',
  WARNING: '#ffd60a',
  INFO: '#0a84ff',
};

export default function SeverityChart() {
  const data = getSeverityDistribution();

  return (
    <div className="glass-panel rounded-xl p-5 animate-fade-in">
      <h3 className="text-xs font-semibold text-text-primary uppercase tracking-wider mb-1">Severity Distribution</h3>
      <p className="text-[10px] text-text-muted mb-4">Breakdown of events by severity level</p>
      <ResponsiveContainer width="100%" height={240}>
        <PieChart>
          <Pie
            data={data}
            dataKey="count"
            nameKey="severity"
            cx="50%"
            cy="50%"
            innerRadius={55}
            outerRadius={85}
            strokeWidth={2}
            stroke="#000000"
          >
            {data.map((entry) => (
              <Cell key={entry.severity} fill={COLORS[entry.severity]} />
            ))}
          </Pie>
          <Tooltip contentStyle={{ backgroundColor: '#0b0f19', border: '1px solid #1f2937', borderRadius: 8, fontSize: 11, color: '#e5e7eb' }} />
          <Legend verticalAlign="bottom" height={36} formatter={(value: string) => <span className="text-[10px] text-text-secondary">{value}</span>} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
