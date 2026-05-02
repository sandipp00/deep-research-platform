import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { Send, Square } from "lucide-react";

interface Props {
  onSend: (text: string) => void;
  onStop?: () => void;
  busy?: boolean;
  placeholder?: string;
}

export default function ChatInput({ onSend, onStop, busy, placeholder }: Props) {
  const [value, setValue] = useState("");
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
      <div className="glass-strong rounded-3xl p-2 pl-4 flex items-end gap-2">
        <textarea
          ref={taRef}
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKey}
          placeholder={placeholder ?? "Ask anything — stocks, news, places, research…"}
          className="flex-1 resize-none bg-transparent outline-none text-zinc-100 placeholder:text-zinc-500 py-2.5 max-h-60"
        />
        {busy && onStop ? (
          <button type="button" onClick={onStop}
                  className="shrink-0 w-10 h-10 rounded-2xl bg-rose-500/20 border border-rose-500/30 grid place-items-center hover:bg-rose-500/30 transition">
            <Square size={14} className="text-rose-300 fill-rose-300" />
          </button>
        ) : (
          <button type="submit" disabled={!value.trim() || busy}
                  className="shrink-0 w-10 h-10 rounded-2xl bg-grad-vivid grid place-items-center text-white shadow-glow disabled:opacity-30 disabled:pointer-events-none transition hover:scale-[1.04] active:scale-95">
            <Send size={16} />
          </button>
        )}
      </div>
      <div className="text-[10px] text-zinc-500 mt-2 px-3">
        ⏎ to send · Shift+⏎ for newline
      </div>
    </form>
  );
}
