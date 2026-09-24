import { motion, useReducedMotion } from "framer-motion";
import "@/styles/motion.css";
import { Sparkles, ExternalLink } from "lucide-react";
import type { Message, Checkpoint, FollowUp } from "@/types";
import BlockRenderer from "./blocks/BlockRenderer";
import CheckpointTrail from "./CheckpointTrail";
import MarkdownBlock from "./blocks/MarkdownBlock";

interface Props {
  message: Message;
  streaming?: boolean;
  checkpoints?: Checkpoint[];
  onFollowUp?: (q: FollowUp) => void;
}

export default function MessageBubble({ message, streaming, checkpoints, onFollowUp }: Props) {
  const isUser = message.role === "user";
  const reduce = useReducedMotion();
  const enter = reduce
    ? { initial: { opacity: 0 }, animate: { opacity: 1 } }
    : {
        initial: { opacity: 0, y: 14, scale: 0.98 },
        animate: { opacity: 1, y: 0, scale: 1 },
        transition: { type: "spring" as const, stiffness: 380, damping: 30, mass: 0.8 },
      };

  if (isUser) {
    return (
      <motion.div
        {...enter}
        className="flex justify-end origin-bottom-right"
      >
        <div className="max-w-[80%] rounded-3xl rounded-tr-md px-4 py-3 bg-ink-800 border border-white/[0.08] text-zinc-100">
          <div className="text-sm whitespace-pre-wrap">{message.content}</div>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div {...enter} className="flex gap-3 origin-bottom-left">
      <motion.div
        animate={streaming && !reduce ? { boxShadow: ["0 0 0 0 rgba(34,197,94,0)", "0 0 16px 2px rgba(34,197,94,0.35)", "0 0 0 0 rgba(34,197,94,0)"] } : { boxShadow: "0 0 0 0 rgba(34,197,94,0)" }}
        transition={streaming ? { duration: 1.8, repeat: Infinity, ease: "easeInOut" } : { duration: 0.3 }}
        className="shrink-0 w-9 h-9 rounded-2xl bg-ink-800 border border-accent-signal/30 grid place-items-center"
      >
        <Sparkles size={16} className="text-accent-signal" />
      </motion.div>
      <div className="flex-1 min-w-0">
        <div className="text-xs font-display font-semibold gradient-text mb-1.5">Lumen</div>

        {checkpoints && checkpoints.length > 0 && (
          <CheckpointTrail items={checkpoints} active={!!streaming} />
        )}

        {message.blocks && message.blocks.length > 0 ? (
          <motion.div
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 10, filter: "blur(4px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
          >
            <BlockRenderer blocks={message.blocks} />
          </motion.div>
        ) : message.content ? (
          <div className="glass rounded-2xl p-4">
            <MarkdownBlock data={{ content: message.content }} />
            {streaming && <span className="stream-caret" aria-hidden />}
          </div>
        ) : streaming ? (
          <ThinkingSkeleton />
        ) : null}

        {message.sources && message.sources.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {message.sources.slice(0, 8).map((url, i) => (
              <motion.a key={i} href={url} target="_blank" rel="noreferrer"
                 initial={{ opacity: 0, y: reduce ? 0 : 6 }}
                 animate={{ opacity: 1, y: 0 }}
                 transition={{ delay: 0.15 + i * 0.04 }}
                 whileHover={reduce ? undefined : { y: -2 }}
                 className="chip hover:bg-white/[0.10] hover:text-white">
                <ExternalLink size={10} />
                {hostnameOf(url)}
              </motion.a>
            ))}
          </div>
        )}

        {message.followUps && message.followUps.length > 0 && onFollowUp && (
          <div className="mt-4 flex flex-wrap gap-2">
            {message.followUps.map((f, i) => (
              <motion.button key={i}
                initial={{ opacity: 0, y: reduce ? 0 : 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 + i * 0.06 }}
                whileHover={reduce ? undefined : { y: -2 }}
                whileTap={reduce ? undefined : { scale: 0.96 }}
                onClick={() => onFollowUp(f)}
                className="px-3 py-1.5 rounded-full text-xs font-medium border border-white/[0.08]
                           bg-white/[0.04] hover:bg-white/[0.08] hover:border-accent-violet/40 transition">
                {f.label}
              </motion.button>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function ThinkingSkeleton() {
  return (
    <div className="glass rounded-2xl p-4 space-y-2.5 max-w-md">
      {[100, 90, 75].map((w, i) => (
        <div
          key={i}
          className="h-3 rounded-full bg-gradient-to-r from-white/[0.04] via-white/[0.10] to-white/[0.04]
                     bg-[length:400px_100%] animate-shimmer"
          style={{ width: `${w}%`, animationDelay: `${i * 120}ms` }}
        />
      ))}
    </div>
  );
}

function hostnameOf(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch { return url; }
}
