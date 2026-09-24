import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ListTodo, Search, Globe, ShieldCheck, Check, Loader2, ExternalLink } from "lucide-react";

interface Step {
  icon: JSX.Element;
  label: string;
  text: string;
}

const QUESTION = "Did this startup really raise the $50M it's claiming?";

const STEPS: Step[] = [
  { icon: <ListTodo size={11} />, label: "plan", text: "Breaking the question into checkable sub-claims" },
  { icon: <Search size={11} />, label: "search", text: "Searching for the funding announcement and round details" },
  { icon: <Globe size={11} />, label: "read", text: "Reading the press release and a TechCrunch report" },
  { icon: <ShieldCheck size={11} />, label: "verify", text: "Cross-checking the amount against the filed regulatory disclosure" },
];

const SOURCES = ["techcrunch.com", "sec.gov", "crunchbase.com"];

const ANSWER =
  "Confirmed — the $50M Series C closed on Mar 4, filed with the SEC at $48.7M plus a $1.3M note.";

const STEP_MS = 1300;
const HOLD_MS = 2600;
const RESET_MS = 900;

export default function AgentTraceDemo() {
  const [stepIndex, setStepIndex] = useState(-1); // -1 = not started
  const [phase, setPhase] = useState<"tracing" | "answered" | "resetting">("tracing");

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    function run(i: number) {
      if (cancelled) return;
      if (i < STEPS.length) {
        setStepIndex(i);
        setPhase("tracing");
        timer = setTimeout(() => run(i + 1), STEP_MS);
      } else {
        setPhase("answered");
        timer = setTimeout(() => {
          setPhase("resetting");
          timer = setTimeout(() => {
            setStepIndex(-1);
            timer = setTimeout(() => run(0), RESET_MS);
          }, 400);
        }, HOLD_MS);
      }
    }

    timer = setTimeout(() => run(0), 500);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, []);

  const visibleSteps = stepIndex >= 0 ? STEPS.slice(0, stepIndex + 1) : [];

  return (
    <div className="rounded-3xl border border-white/[0.08] bg-white/[0.03] p-5 sm:p-6 text-left max-w-xl mx-auto overflow-hidden">
      <div className="flex items-center gap-2 pb-4 mb-4 border-b border-white/[0.06]">
        <span className="w-2 h-2 rounded-full bg-accent-signal animate-pulse" />
        <span className="text-[11px] font-mono uppercase tracking-wider text-zinc-500">Live trace</span>
      </div>

      <div className="text-sm text-zinc-200 mb-4">{QUESTION}</div>

      <ol className="relative min-h-[132px]">
        <div className="absolute left-[7px] top-1.5 bottom-1.5 w-px bg-gradient-to-b from-accent-signal/40 to-transparent" />
        <AnimatePresence initial={false}>
          {visibleSteps.map((s, i) => {
            const isLast = i === visibleSteps.length - 1;
            const inProgress = phase === "tracing" && isLast;
            return (
              <motion.li
                key={s.label}
                initial={{ opacity: 0, x: -6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.25, ease: "easeOut" }}
                className="relative pl-6 pb-2.5 last:pb-0 flex items-start gap-2"
              >
                <span
                  className={`absolute left-0 top-0.5 w-3.5 h-3.5 rounded-full grid place-items-center ring-2 ring-ink-900 ${
                    inProgress
                      ? "bg-accent-signal text-ink-950 shadow-[0_0_10px_rgba(34,197,94,0.6)] animate-pulse"
                      : "bg-accent-signal/90 text-ink-950"
                  }`}
                >
                  {inProgress ? <Loader2 size={8} className="animate-spin" /> : <Check size={8} />}
                </span>
                <span className="text-xs leading-snug text-zinc-300">{s.text}</span>
                <span className="ml-auto hidden sm:inline-flex items-center gap-1 rounded-full bg-white/[0.05] border border-white/[0.06] px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-wider text-zinc-500 shrink-0">
                  {s.icon}
                  {s.label}
                </span>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ol>

      <AnimatePresence>
        {(phase === "answered" || phase === "resetting") && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: phase === "answered" ? 1 : 0, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className="mt-3 pt-3 border-t border-white/[0.06]"
          >
            <p className="text-sm text-zinc-100 leading-relaxed">{ANSWER}</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {SOURCES.map((s) => (
                <span
                  key={s}
                  className="inline-flex items-center gap-1.5 rounded-full bg-white/[0.06] border border-white/[0.08] px-3 py-1 text-[11px] font-medium text-zinc-400"
                >
                  <ExternalLink size={10} />
                  {s}
                </span>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
