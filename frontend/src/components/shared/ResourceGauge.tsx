interface ResourceGaugeProps {
  readonly label: string;
  readonly value: number;
  readonly color: string;
  readonly size?: number;
}

export default function ResourceGauge({
  label,
  value,
  color,
  size = 80,
}: ResourceGaugeProps) {
  const radius = (size - 8) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (value / 100) * circumference;
  const center = size / 2;

  // Color intensity based on usage
  const isHigh = value > 85;

  return (
    <div className="flex flex-col items-center gap-1.5">
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={center} cy={center} r={radius} fill="none" stroke="#1f2937" strokeWidth="4" />
        <circle
          cx={center}
          cy={center}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-700 ease-out"
          style={isHigh ? { filter: `drop-shadow(0 0 4px ${color})` } : {}}
        />
      </svg>
      <div className="absolute flex flex-col items-center justify-center" style={{ width: size, height: size }}>
        <span className={`text-sm font-bold ${isHigh ? 'text-accent-red' : 'text-text-primary'}`}>{value}%</span>
      </div>
      <span className="text-[10px] font-semibold text-text-muted uppercase tracking-wider">{label}</span>
    </div>
  );
}
