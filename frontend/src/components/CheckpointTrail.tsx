import { motion, AnimatePresence } from "framer-motion";
import {
  Search, Globe, FileText, MapPin, Newspaper, TrendingUp,
  DollarSign, Bitcoin, BookOpen, ListTodo, Loader2, Check, Sparkles,
} from "lucide-react";
import type { Checkpoint } from "@/types";

const TOOL_ICON: Record<string, JSX.Element> = {
  web_search:       <Search size={12} />,
  read_webpage:     <Globe size={12} />,
  wiki_search:      <BookOpen size={12} />,
  nearby_places:    <MapPin size={12} />,
  latest_news:      <Newspaper size={12} />,
  get_stock_price:  <TrendingUp size={12} />,
  get_forex_rate:   <DollarSign size={12} />,
  get_crypto_price: <Bitcoin size={12} />,
  write_todos:      <ListTodo size={12} />,
};

export default function CheckpointTrail({ items, active }: { items: Checkpoint[]; active: boolean }) {
  if (items.length === 0) return null;

  return (
    <div className="glass rounded-2xl p-3 mb-3 inline-block max-w-full">
      <div className="flex items-center gap-1.5 mb-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
        <Sparkles size={10} className="text-accent-pink" />
        {active ? "Working on it" : "How I got here"}
      </div>
      <ol className="relative">
        {/* timeline rail */}
        <div className="absolute left-[7px] top-1.5 bottom-1.5 w-px bg-gradient-to-b from-accent-violet/40 via-accent-pink/30 to-transparent" />
        <AnimatePresence initial={false}>
          {items.map((c, i) => {
            const isLast = i === items.length - 1;
            const inProgress = active && isLast;
            const icon = c.tool ? TOOL_ICON[c.tool] : null;
            return (
              <motion.li
                key={i}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.22, ease: "easeOut" }}
                className="relative pl-6 pb-1.5 last:pb-0 flex items-start gap-2"
              >
                <span
                  className={`absolute left-0 top-0.5 w-3.5 h-3.5 rounded-full grid place-items-center ring-2 ring-ink-900
                    ${inProgress
                      ? "bg-accent-violet text-white animate-pulse"
                      : "bg-emerald-500/90 text-white"}`}
                >
                  {inProgress ? <Loader2 size={8} className="animate-spin" />
                              : icon ?? <Check size={8} />}
                </span>
                <span className={`text-xs leading-snug ${inProgress ? "text-zinc-200" : "text-zinc-400"}`}>
                  {c.content}
                </span>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ol>
    </div>
  );
}
