import { motion } from "framer-motion";
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

  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex justify-end"
      >
        <div className="max-w-[80%] rounded-3xl rounded-tr-md px-4 py-3 bg-grad-vivid text-white shadow-glow">
          <div className="text-sm whitespace-pre-wrap">{message.content}</div>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex gap-3"
    >
      <div className="shrink-0 w-9 h-9 rounded-2xl bg-grad-vivid grid place-items-center shadow-glow">
        <Sparkles size={16} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-xs font-display font-semibold gradient-text mb-1.5">Lumen</div>

        {checkpoints && checkpoints.length > 0 && (
          <CheckpointTrail items={checkpoints} active={!!streaming} />
        )}

        {message.blocks && message.blocks.length > 0 ? (
          <BlockRenderer blocks={message.blocks} />
        ) : message.content ? (
          <div className="glass rounded-2xl p-4">
            <MarkdownBlock data={{ content: message.content }} />
          </div>
        ) : streaming ? (
          <div className="text-sm text-zinc-400 italic">Thinking…</div>
        ) : null}

        {message.sources && message.sources.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {message.sources.slice(0, 8).map((url, i) => (
              <a key={i} href={url} target="_blank" rel="noreferrer"
                 className="chip hover:bg-white/[0.10] hover:text-white">
                <ExternalLink size={10} />
                {hostnameOf(url)}
              </a>
            ))}
          </div>
        )}

        {message.followUps && message.followUps.length > 0 && onFollowUp && (
          <div className="mt-4 flex flex-wrap gap-2">
            {message.followUps.map((f, i) => (
              <button key={i}
                onClick={() => onFollowUp(f)}
                className="px-3 py-1.5 rounded-full text-xs font-medium border border-white/[0.08]
                           bg-white/[0.04] hover:bg-white/[0.08] hover:border-accent-violet/40 transition">
                {f.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function hostnameOf(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); }
  catch { return url; }
}
