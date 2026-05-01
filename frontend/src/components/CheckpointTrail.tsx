import { motion, AnimatePresence } from "framer-motion";
import { Loader2 } from "lucide-react";
import type { Checkpoint } from "@/types";

export default function CheckpointTrail({ items, active }: { items: Checkpoint[]; active: boolean }) {
  if (items.length === 0) return null;
  return (
    <div className="space-y-1.5 mb-3">
      <AnimatePresence initial={false}>
        {items.map((c, i) => {
          const isLast = i === items.length - 1;
          return (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
              className="flex items-center gap-2 text-xs"
            >
              {active && isLast ? (
                <Loader2 size={12} className="animate-spin text-accent-cyan" />
              ) : (
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/80" />
              )}
              <span className={isLast && active ? "text-zinc-300" : "text-zinc-500"}>
                {c.content}
              </span>
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}
