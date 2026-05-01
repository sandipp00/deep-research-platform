import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { BarChartData } from "@/types";

export default function BarChartBlock({ data }: { data: BarChartData }) {
  const points = (data.points ?? []).map((p) => ({ name: p.label, value: p.value }));

  return (
    <div className="glass rounded-2xl p-4">
      <div className="text-sm text-zinc-400 mb-2">
        {data.x_axis} → {data.y_axis}
      </div>
      <div style={{ width: "100%", height: 280 }}>
        <ResponsiveContainer>
          <BarChart data={points} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <defs>
              <linearGradient id="grad-bar" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#8b5cf6" />
                <stop offset="100%" stopColor="#ec4899" />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey="name" stroke="rgba(255,255,255,0.5)" fontSize={12} />
            <YAxis stroke="rgba(255,255,255,0.5)" fontSize={12} />
            <Tooltip
              contentStyle={{
                background: "#15152a",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 12,
                fontSize: 13,
              }}
              cursor={{ fill: "rgba(255,255,255,0.04)" }}
            />
            <Bar dataKey="value" fill="url(#grad-bar)" radius={[8, 8, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
