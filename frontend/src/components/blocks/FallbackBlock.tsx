import { useState } from "react";
import { ChevronDown, ChevronUp, FileQuestion } from "lucide-react";

export default function FallbackBlock({ template_id, data }: { template_id: string; data: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="glass rounded-2xl p-4">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 text-sm font-medium text-zinc-300 hover:text-white"
      >
        <FileQuestion size={16} className="text-accent-cyan" />
        Unknown block: <code className="font-mono text-accent-cyan">{template_id}</code>
        {open ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </button>
      {open && (
        <pre className="mt-3 text-xs bg-ink-900 border border-white/[0.06] rounded-xl p-3 overflow-auto max-h-96 text-zinc-300">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
