import { motion } from "framer-motion";
import { Info, AlertTriangle, CheckCircle2 } from "lucide-react";
import type { InsightCardsData, InsightItem } from "@/types";

const SEVERITY_STYLES: Record<NonNullable<InsightItem["severity"]>, { bg: string; ring: string; icon: JSX.Element; text: string }> = {
  info:    { bg: "from-cyan-500/15 to-violet-500/10",   ring: "ring-cyan-400/30",   icon: <Info size={16} />,         text: "text-cyan-300" },
  success: { bg: "from-emerald-500/15 to-cyan-500/10",  ring: "ring-emerald-400/30",icon: <CheckCircle2 size={16} />, text: "text-emerald-300" },
  warning: { bg: "from-rose-500/15 to-amber-500/10",    ring: "ring-rose-400/30",   icon: <AlertTriangle size={16} />,text: "text-rose-300" },
};

export default function InsightCardsBlock({ data }: { data: InsightCardsData }) {
  const items = data.items ?? [];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {items.map((item, i) => {
        const sev = item.severity || "info";
        const s = SEVERITY_STYLES[sev];
        return (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05, duration: 0.3 }}
            className={`relative rounded-2xl p-4 border border-white/[0.06] bg-gradient-to-br ${s.bg} ring-1 ${s.ring}`}
          >
            <div className={`flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider ${s.text}`}>
              {s.icon}
              <span>{sev}</span>
            </div>
            <div className="mt-2 font-display font-semibold text-zinc-50">{item.title}</div>
            <div className="mt-1 text-sm text-zinc-300 leading-relaxed">{item.body}</div>
          </motion.div>
        );
      })}
    </div>
  );
}
