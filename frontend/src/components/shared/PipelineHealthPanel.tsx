import { Activity, Database, Server, Zap } from 'lucide-react';
import { Area, AreaChart, ResponsiveContainer } from 'recharts';

// Mock data for the sparklines
const latencyData = Array.from({ length: 20 }, (_, i) => ({
  time: i,
  value: 40 + Math.random() * 20,
}));

const epsData = Array.from({ length: 20 }, (_, i) => ({
  time: i,
  value: 300 + Math.random() * 100,
}));

export default function PipelineHealthPanel() {
  return (
    <div className="glass-panel rounded-xl p-5 border border-accent-blue/20">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-bold text-text-primary flex items-center gap-2">
            <Activity className="w-4 h-4 text-accent-blue" />
            Pipeline Health
          </h3>
          <p className="text-xs text-text-muted mt-0.5">Real-time metrics from Kafka & PostgreSQL</p>
        </div>
        
        {/* Grafana Links */}
        <div className="flex gap-2">
          <a
            href="http://localhost:3000/d/pipeline_overview"
            target="_blank"
            rel="noopener noreferrer"
            className="px-2 py-1 text-[10px] font-medium rounded bg-bg-surface border border-border-light hover:border-accent-blue hover:text-accent-blue transition-colors text-text-secondary flex items-center gap-1"
          >
            Pipeline Overview
          </a>
          <a
            href="http://localhost:3000/d/kafka_monitoring"
            target="_blank"
            rel="noopener noreferrer"
            className="px-2 py-1 text-[10px] font-medium rounded bg-bg-surface border border-border-light hover:border-accent-purple hover:text-accent-purple transition-colors text-text-secondary flex items-center gap-1"
          >
            Kafka
          </a>
          <a
            href="http://localhost:3000/d/system_health"
            target="_blank"
            rel="noopener noreferrer"
            className="px-2 py-1 text-[10px] font-medium rounded bg-bg-surface border border-border-light hover:border-accent-green hover:text-accent-green transition-colors text-text-secondary flex items-center gap-1"
          >
            System Health
          </a>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* EPS */}
        <div className="bg-bg-surface/50 rounded-lg p-3 border border-border-light/50 flex flex-col justify-between">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-accent-blue" />
            <span className="text-xs font-semibold text-text-secondary">Events/Sec</span>
          </div>
          <div className="flex items-end justify-between">
            <div>
              <span className="text-2xl font-bold text-text-primary">342</span>
              <span className="text-[10px] text-accent-green ml-2">+5%</span>
            </div>
            <div className="h-8 w-16">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={epsData}>
                  <defs>
                    <linearGradient id="colorEps" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <Area type="monotone" dataKey="value" stroke="#3b82f6" fillOpacity={1} fill="url(#colorEps)" isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Latency */}
        <div className="bg-bg-surface/50 rounded-lg p-3 border border-border-light/50 flex flex-col justify-between">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-4 h-4 text-accent-green" />
            <span className="text-xs font-semibold text-text-secondary">Processing Latency</span>
          </div>
          <div className="flex items-end justify-between">
            <div>
              <span className="text-2xl font-bold text-text-primary">45ms</span>
            </div>
            <div className="h-8 w-16">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={latencyData}>
                  <defs>
                    <linearGradient id="colorLat" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#10b981" stopOpacity={0.3}/>
                      <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <Area type="monotone" dataKey="value" stroke="#10b981" fillOpacity={1} fill="url(#colorLat)" isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>

        {/* Kafka Lag */}
        <div className="bg-bg-surface/50 rounded-lg p-3 border border-border-light/50 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Server className="w-4 h-4 text-accent-purple" />
                <span className="text-xs font-semibold text-text-secondary">Kafka Lag</span>
              </div>
              <span className="text-2xl font-bold text-text-primary">0</span>
              <p className="text-[10px] text-text-muted mt-1">Optimal</p>
            </div>
             <div className="w-10 h-10 rounded-full bg-accent-purple/10 flex flex-col items-center justify-center border border-accent-purple/30">
                <div className="w-2 h-2 rounded-full bg-accent-purple animate-pulse"></div>
            </div>
        </div>

        {/* DB Write Rate */}
        <div className="bg-bg-surface/50 rounded-lg p-3 border border-border-light/50 flex items-center justify-between">
             <div>
              <div className="flex items-center gap-2 mb-2">
                <Database className="w-4 h-4 text-accent-cyan" />
                <span className="text-xs font-semibold text-text-secondary">DB Write Rate</span>
              </div>
              <span className="text-2xl font-bold text-text-primary">340/s</span>
              <p className="text-[10px] text-text-muted mt-1">PostgreSQL Sync</p>
            </div>
            <div className="w-10 h-10 rounded-full bg-accent-cyan/10 flex flex-col items-center justify-center border border-accent-cyan/30">
               <Database className="w-4 h-4 text-accent-cyan" />
            </div>
        </div>

      </div>
    </div>
  );
}
