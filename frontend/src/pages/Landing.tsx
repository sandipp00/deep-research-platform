import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Sparkles,
  MessageCircleQuestion,
  Workflow,
  BadgeCheck,
  X,
  Check,
  ArrowRight,
  Github,
} from "lucide-react";
import { useAuth } from "@/store/auth";
import ThemeToggle from "@/components/ThemeToggle";
import AgentTraceDemo from "@/components/AgentTraceDemo";

const HOW_IT_WORKS = [
  {
    icon: MessageCircleQuestion,
    title: "Ask anything",
    desc: "Stocks, news, nearby places, a claim you want checked — one box, no setup.",
  },
  {
    icon: Workflow,
    title: "Watch it work, live",
    desc: "The agent plans, searches, reads and cross-checks in real time — every step streamed as it happens, not hidden behind a spinner.",
  },
  {
    icon: BadgeCheck,
    title: "Get a sourced answer",
    desc: "Every claim ties back to a real source you can click through and verify yourself.",
  },
];

const GENERIC_ANSWER =
  "Yes, that funding round happened and the amount sounds about right based on what's publicly known.";

const LUMEN_ANSWER =
  "Confirmed — the $50M Series C closed Mar 4, filed with the SEC at $48.7M plus a $1.3M note.";

export default function Landing() {
  const user = useAuth((s) => s.user);

  return (
    <div className="min-h-screen bg-white text-zinc-900 dark:bg-ink-950 dark:text-zinc-100 transition-colors">
      <div
        className="pointer-events-none fixed inset-0 opacity-0 dark:opacity-100 transition-opacity"
        style={{
          backgroundImage:
            "radial-gradient(at 15% 0%, rgba(34,197,94,0.10), transparent 45%), radial-gradient(at 100% 100%, rgba(34,197,94,0.05), transparent 55%)",
        }}
      />

      <div className="relative">
        {/* Nav */}
        <header className="max-w-6xl mx-auto flex items-center justify-between px-6 py-6">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-accent-signal grid place-items-center shadow-glow">
              <Sparkles size={16} className="text-ink-950" />
            </div>
            <span className="font-display font-bold text-lg">Lumen</span>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            {user ? (
              <Link to="/app" className="btn-primary text-sm !px-4 !py-2">
                Open Lumen <ArrowRight size={14} />
              </Link>
            ) : (
              <>
                <Link
                  to="/login"
                  className="hidden sm:inline-flex text-sm font-medium px-3 py-2 text-zinc-600 hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-white transition"
                >
                  Sign in
                </Link>
                <Link to="/register" className="btn-primary text-sm !px-4 !py-2">
                  Get started <ArrowRight size={14} />
                </Link>
              </>
            )}
          </div>
        </header>

        {/* Hero */}
        <section className="max-w-3xl mx-auto text-center px-6 pt-14 pb-10">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-xs font-medium
              border border-zinc-200 text-zinc-600 bg-zinc-50
              dark:border-white/[0.08] dark:text-zinc-300 dark:bg-white/[0.04]"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-accent-signal animate-pulse" />
            Watch it research, live — not a demo video
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.05 }}
            className="mt-6 font-display font-bold text-4xl sm:text-5xl leading-[1.1] tracking-tight"
          >
            Ask a hard question.<br />Watch Lumen prove the answer.
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="mt-5 text-lg text-zinc-600 dark:text-zinc-400 max-w-xl mx-auto"
          >
            A research agent that plans, searches, reads and cites in the open — so you see exactly
            how it got to an answer, not just the answer.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.15 }}
            className="mt-8 flex items-center justify-center gap-3"
          >
            <Link to={user ? "/app" : "/register"} className="btn-primary">
              {user ? "Open Lumen" : "Start researching"} <ArrowRight size={16} />
            </Link>
            <a
              href="https://github.com/AnirudhGupta007/deep-research-platform"
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-2xl px-6 py-3 font-medium
                border border-zinc-200 text-zinc-700 hover:bg-zinc-50
                dark:border-white/[0.08] dark:text-zinc-200 dark:hover:bg-white/[0.06] transition"
            >
              <Github size={16} /> View source
            </a>
          </motion.div>
        </section>

        {/* Live trace demo — the hero visual */}
        <section className="px-6 pb-24">
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
          >
            <AgentTraceDemo />
          </motion.div>
        </section>

        {/* Before / after */}
        <section className="max-w-5xl mx-auto px-6 pb-24">
          <div className="text-center max-w-xl mx-auto mb-10">
            <h2 className="font-display font-bold text-3xl">Same question. Different rigor.</h2>
            <p className="mt-3 text-zinc-600 dark:text-zinc-400">
              A generic chatbot guesses from memory. Lumen goes and checks.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 gap-4">
            <div className="rounded-3xl p-6 border border-zinc-200 bg-zinc-50 dark:border-white/[0.06] dark:bg-white/[0.02]">
              <div className="flex items-center gap-2 mb-4 text-xs font-semibold uppercase tracking-wider text-zinc-400">
                <X size={14} className="text-rose-400" />
                Generic chatbot
              </div>
              <p className="text-sm text-zinc-500 dark:text-zinc-500 italic leading-relaxed">
                {GENERIC_ANSWER}
              </p>
              <p className="mt-3 text-xs text-zinc-400 dark:text-zinc-600">No sources. No way to verify.</p>
            </div>

            <div className="rounded-3xl p-6 border border-accent-signal/30 bg-accent-signal/[0.04]">
              <div className="flex items-center gap-2 mb-4 text-xs font-semibold uppercase tracking-wider text-accent-signal">
                <Check size={14} />
                Lumen
              </div>
              <p className="text-sm text-zinc-800 dark:text-zinc-200 leading-relaxed">{LUMEN_ANSWER}</p>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {["techcrunch.com", "sec.gov"].map((s) => (
                  <span
                    key={s}
                    className="chip !bg-white/[0.05] !border-white/[0.08] text-zinc-500 dark:text-zinc-400"
                  >
                    {s}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* How it works */}
        <section className="max-w-5xl mx-auto px-6 pb-24">
          <div className="text-center max-w-xl mx-auto mb-12">
            <h2 className="font-display font-bold text-3xl">How it works</h2>
            <p className="mt-3 text-zinc-600 dark:text-zinc-400">
              Eight specialized tools — search, page reading, maps, markets, news — picked
              automatically, one per sub-question.
            </p>
          </div>

          <div className="grid sm:grid-cols-3 gap-5">
            {HOW_IT_WORKS.map(({ icon: Icon, title, desc }, i) => (
              <motion.div
                key={title}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.35, delay: i * 0.08 }}
                className="rounded-3xl p-6 border border-zinc-200 bg-white dark:border-white/[0.06] dark:bg-white/[0.03]"
              >
                <div className="w-9 h-9 rounded-xl bg-accent-signal/15 grid place-items-center mb-4">
                  <Icon size={17} className="text-accent-signal" />
                </div>
                <div className="font-display font-bold text-base">{title}</div>
                <div className="text-sm text-zinc-500 dark:text-zinc-400 mt-1.5 leading-relaxed">
                  {desc}
                </div>
              </motion.div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="max-w-4xl mx-auto px-6 pb-24">
          <div className="rounded-4xl p-10 text-center border border-zinc-200 bg-zinc-50 dark:border-white/[0.08] dark:bg-white/[0.04]">
            <h2 className="font-display font-bold text-2xl sm:text-3xl">
              Ask something worth researching.
            </h2>
            <p className="mt-3 text-zinc-600 dark:text-zinc-400">
              Free to try. No credit card required.
            </p>
            <Link to={user ? "/app" : "/register"} className="btn-primary mt-6">
              {user ? "Open Lumen" : "Create a free account"} <ArrowRight size={16} />
            </Link>
          </div>
        </section>

        {/* Footer */}
        <footer className="max-w-6xl mx-auto px-6 py-8 flex items-center justify-between text-xs text-zinc-400 dark:text-zinc-500 border-t border-zinc-200 dark:border-white/[0.06]">
          <span>© {new Date().getFullYear()} Lumen — research, illuminated.</span>
          <span>Built with LangGraph, Deep Agents &amp; DeepSeek</span>
        </footer>
      </div>
    </div>
  );
}
