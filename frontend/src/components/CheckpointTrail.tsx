import { motion, AnimatePresence } from "framer-motion";
import {
  Search, Globe, FileText, MapPin, Newspaper, TrendingUp,
  DollarSign, Bitcoin, BookOpen, ListTodo, Loader2, Check, Sparkles,
} from "lucide-react";
import type { Checkpoint } from "@/types";

const TOOL_ICON: Record<string, JSX.Element> = {
  web_search:       <Search size={11} />,
  read_webpage:     <Globe size={11} />,
  wiki_search:      <BookOpen size={11} />,
  nearby_places:    <MapPin size={11} />,
  latest_news:      <Newspaper size={11} />,
  get_stock_price:  <TrendingUp size={11} />,
  get_forex_rate:   <DollarSign size={11} />,
  get_crypto_price: <Bitcoin size={11} />,
  write_todos:      <ListTodo size={11} />,
};

const TOOL_LABEL: Record<string, string> = {
  web_search: "search",
  read_webpage: "read",
  wiki_search: "wiki",
  nearby_places: "nearby",
  latest_news: "news",
  get_stock_price: "stock",
  get_forex_rate: "forex",
  get_crypto_price: "crypto",
  write_todos: "plan",
};

function fmtElapsed(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60_000)}m ${Math.floor((ms % 60_000) / 1000)}s`;
}

export default function CheckpointTrail({ items, active }: { items: Checkpoint[]; active: boolean }) {
  if (items.length === 0) return null;
  const first = items[0]?.ts ?? Date.now();

  return (
    <div className="glass rounded-2xl p-3 mb-3 inline-block max-w-full relative overflow-hidden">
      {active && (
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px
                        bg-gradient-to-r from-transparent via-accent-pink/60 to-transparent
                        animate-shimmer" />
      )}
      <div className="flex items-center gap-1.5 mb-2 text-[10px] font-semibold uppercase tracking-wider text-zinc-400">
        <Sparkles size={10} className="text-accent-pink" />
        {active ? "Working on it" : "How I got here"}
        <span className="ml-auto text-zinc-500 font-mono normal-case tracking-normal">
          {items.length} step{items.length === 1 ? "" : "s"}
        </span>
      </div>
      <ol className="relative">
        <div className="absolute left-[7px] top-1.5 bottom-1.5 w-px bg-gradient-to-b from-accent-violet/40 via-accent-pink/30 to-transparent" />
        <AnimatePresence initial={false}>
          {items.map((c, i) => {
            const isLast = i === items.length - 1;
            const inProgress = active && isLast;
            const icon = c.tool ? TOOL_ICON[c.tool] : null;
            const label = c.tool ? TOOL_LABEL[c.tool] : null;
            const elapsed = c.ts ? c.ts - first : null;
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
                      ? "bg-accent-violet text-white shadow-[0_0_10px_rgba(139,92,246,0.6)] animate-pulse"
                      : "bg-emerald-500/90 text-white"}`}
                >
                  {inProgress ? <Loader2 size={8} className="animate-spin" />
                              : icon ?? <Check size={8} />}
                </span>
                <span className={`text-xs leading-snug ${inProgress ? "text-zinc-200" : "text-zinc-400"}`}>
                  {c.content}
                </span>
                <span className="ml-auto flex items-center gap-1.5 shrink-0 pl-2">
                  {label && (
                    <span className="hidden sm:inline-flex items-center gap-1 rounded-full
                                     bg-white/[0.05] border border-white/[0.06] px-1.5 py-0.5
                                     text-[9px] font-mono uppercase tracking-wider text-zinc-400">
                      {icon}{label}
                    </span>
                  )}
                  {elapsed !== null && (
                    <span className="text-[9px] font-mono text-zinc-500 tabular-nums">
                      +{fmtElapsed(elapsed)}
                    </span>
                  )}
                </span>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ol>
    </div>
  );
}
