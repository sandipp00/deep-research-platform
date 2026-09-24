import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Send, Square } from "lucide-react";
import "@/styles/motion.css";

interface Props {
  onSend: (text: string) => void;
  onStop?: () => void;
  busy?: boolean;
  placeholder?: string;
}

export default function ChatInput({ onSend, onStop, busy, placeholder }: Props) {
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const reduce = useReducedMotion();
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (taRef.current) {
      taRef.current.style.height = "auto";
      taRef.current.style.height = Math.min(taRef.current.scrollHeight, 240) + "px";
    }
  }, [value]);

  function submit(e?: FormEvent) {
    e?.preventDefault();
    const v = value.trim();
    if (!v || busy) return;
    onSend(v);
    setValue("");
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Skip during IME composition (Chinese/Japanese/Korean input, mobile predictive)
    if ((e.nativeEvent as any).isComposing || e.keyCode === 229) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <form onSubmit={submit} className="relative">
      <div className="glass-strong rounded-3xl p-2 pl-4 flex items-end gap-2 relative">
        <motion.div
          aria-hidden
          initial={false}
          animate={{ opacity: focused ? 1 : 0 }}
          transition={{ duration: 0.25 }}
          className="pointer-events-none absolute -inset-px rounded-3xl"
        >
          <div className="input-ring absolute inset-0 rounded-3xl border border-accent-signal/50 shadow-[0_0_24px_rgba(34,197,94,0.22)]" />
        </motion.div>
        <textarea
          ref={taRef}
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKey}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={placeholder ?? "Ask anything — stocks, news, places, research…"}
          className="flex-1 resize-none bg-transparent outline-none text-zinc-100 placeholder:text-zinc-500 py-2.5 max-h-60"
        />
        <AnimatePresence mode="wait" initial={false}>
        {busy && onStop ? (
          <motion.button key="stop" type="button" onClick={onStop} aria-label="Stop"
                  initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.6, opacity: 0 }}
                  whileTap={reduce ? undefined : { scale: 0.9 }}
                  className="shrink-0 w-10 h-10 rounded-2xl bg-rose-500/20 border border-rose-500/30 grid place-items-center hover:bg-rose-500/30 transition-colors">
            <Square size={14} className="text-rose-300 fill-rose-300" />
          </motion.button>
        ) : (
          <motion.button key="send" type="submit" disabled={!value.trim() || busy} aria-label="Send"
                  initial={{ scale: 0.6, opacity: 0 }}
                  animate={{ scale: 1, opacity: value.trim() ? 1 : 0.3 }}
                  exit={{ scale: 0.6, opacity: 0 }}
                  whileHover={reduce || !value.trim() ? undefined : { scale: 1.06 }}
                  whileTap={reduce ? undefined : { scale: 0.88 }}
                  className="shrink-0 w-10 h-10 rounded-2xl bg-accent-signal grid place-items-center text-ink-950 shadow-glow disabled:pointer-events-none">
            <motion.span animate={{ x: value.trim() && !reduce ? 1 : 0, y: value.trim() && !reduce ? -1 : 0 }} className="grid place-items-center">
              <Send size={16} />
            </motion.span>
          </motion.button>
        )}
        </AnimatePresence>
      </div>
      <div className="text-[10px] text-zinc-500 mt-2 px-3">
        ⏎ to send · Shift+⏎ for newline
      </div>
    </form>
  );
}
