import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Sparkles,
  Search,
  Map,
  Newspaper,
  TrendingUp,
  Landmark,
  Bitcoin,
  FileText,
  BookOpen,
  Zap,
  Timer,
  DollarSign,
  ArrowRight,
  Github,
} from "lucide-react";
import { useAuth } from "@/store/auth";
import ThemeToggle from "@/components/ThemeToggle";

const FEATURES = [
  {
    icon: Search,
    title: "Live web search",
    desc: "Octen-powered search with highlighted, LLM-ready snippets — Tavily and DuckDuckGo as automatic fallbacks.",
  },
  {
    icon: FileText,
    title: "Read any page or PDF",
    desc: "Jina Reader strips a URL down to clean text, including government filings and annual reports.",
  },
  {
    icon: BookOpen,
    title: "Wikipedia grounding",
    desc: "Fast factual lookups for definitions, history, and general knowledge before the agent goes deep.",
  },
  {
    icon: Map,
    title: "Nearby places, on a map",
    desc: "OpenStreetMap + Overpass finds fuel stops, EV chargers, ATMs and pharmacies, rendered on an interactive Leaflet map.",
  },
  {
    icon: Newspaper,
    title: "Breaking news",
    desc: "Live RSS from NDTV, Economic Times, Moneycontrol and Times of India for anything under an hour old.",
  },
  {
    icon: TrendingUp,
    title: "Stock prices",
    desc: "Real-time NSE, BSE and global equities — price, change, P/E and 52-week range in one call.",
  },
  {
    icon: Landmark,
    title: "FX rates",
    desc: "Live currency conversion across any pair, sourced straight from Frankfurter.",
  },
  {
    icon: Bitcoin,
    title: "Crypto prices",
    desc: "INR and USD pricing with 24h change for every major coin, via CoinGecko.",
  },
];

const STATS = [
  {
    icon: Zap,
    stat: "DeepSeek V4.1 Flash",
    label: "primary reasoning model",
    detail: "1M-token context, routed through OpenRouter with automatic provider failover",
  },
  {
    icon: DollarSign,
    stat: "$0.15 / $0.60",
    label: "per million tokens (in / out)",
    detail: "a fraction of frontier-model pricing, with ephemeral prompt caching on top",
  },
  {
    icon: Timer,
    stat: "Sub-second search",
    label: "Octen web search API",
    detail: "purpose-built search infra for agentic workloads, cached in Redis on repeat queries",
  },
];

export default function Landing() {
  const user = useAuth((s) => s.user);

  return (
    <div className="min-h-screen bg-white text-zinc-900 dark:bg-ink-950 dark:text-zinc-100 transition-colors">
      {/* ambient glow — dark mode only */}
      <div
        className="pointer-events-none fixed inset-0 opacity-0 dark:opacity-100 transition-opacity"
        style={{
          backgroundImage:
            "radial-gradient(at 10% 0%, rgba(139,92,246,0.16), transparent 45%), radial-gradient(at 90% 10%, rgba(236,72,153,0.12), transparent 50%), radial-gradient(at 50% 100%, rgba(34,211,238,0.09), transparent 55%)",
        }}
      />

      <div className="relative">
        {/* Nav */}
        <header className="max-w-6xl mx-auto flex items-center justify-between px-6 py-6">
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-grad-vivid grid place-items-center shadow-glow">
              <Sparkles size={16} className="text-white" />
            </div>
            <span className="font-display font-bold text-lg dark:gradient-text">Lumen</span>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            {user ? (
              <Link
                to="/app"
                className="inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-semibold text-white bg-grad-vivid shadow-glow hover:scale-[1.02] active:scale-95 transition"
              >
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
                <Link
                  to="/register"
                  className="inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-semibold text-white bg-grad-vivid shadow-glow hover:scale-[1.02] active:scale-95 transition"
                >
                  Get started <ArrowRight size={14} />
                </Link>
              </>
            )}
          </div>
        </header>

        {/* Hero */}
        <section className="max-w-4xl mx-auto text-center px-6 pt-16 pb-20">
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="inline-flex items-center gap-2 rounded-full px-3.5 py-1.5 text-xs font-medium
              border border-zinc-200 text-zinc-600 bg-zinc-50
              dark:border-white/[0.08] dark:text-zinc-300 dark:bg-white/[0.04]"
          >
            <Zap size={12} className="text-accent-violet" />
            Now running on DeepSeek V4.1 Flash + Octen search
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.05 }}
            className="mt-6 font-display font-bold text-5xl sm:text-6xl leading-[1.05] tracking-tight"
          >
            Research,{" "}
            <span className="bg-clip-text text-transparent bg-grad-vivid">illuminated.</span>
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="mt-5 text-lg text-zinc-600 dark:text-zinc-400 max-w-2xl mx-auto"
          >
            A deep research agent that plans, searches, reads and cites — streaming every step
            live. Eight specialized tools, one conversation, real sources every time.
          </motion.p>

          <motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.15 }}
            className="mt-8 flex items-center justify-center gap-3"
          >
            <Link
              to={user ? "/app" : "/register"}
              className="inline-flex items-center gap-2 rounded-2xl px-6 py-3 font-semibold text-white bg-grad-vivid shadow-glow hover:scale-[1.02] active:scale-95 transition"
            >
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

        {/* Stats strip */}
        <section className="max-w-5xl mx-auto px-6 pb-20">
          <div className="grid sm:grid-cols-3 gap-4">
            {STATS.map(({ icon: Icon, stat, label, detail }, i) => (
              <motion.div
                key={label}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.4, delay: i * 0.05 }}
                className="rounded-3xl p-6 border
                  border-zinc-200 bg-zinc-50
                  dark:border-white/[0.06] dark:bg-white/[0.03]"
              >
                <div className="w-9 h-9 rounded-xl bg-grad-vivid grid place-items-center mb-4 shadow-glow">
                  <Icon size={16} className="text-white" />
                </div>
                <div className="font-display font-bold text-xl">{stat}</div>
                <div className="text-sm text-zinc-500 dark:text-zinc-400 mt-0.5">{label}</div>
                <div className="text-xs text-zinc-400 dark:text-zinc-500 mt-2 leading-relaxed">
                  {detail}
                </div>
              </motion.div>
            ))}
          </div>
        </section>

        {/* Features */}
        <section className="max-w-6xl mx-auto px-6 pb-24">
          <div className="text-center max-w-xl mx-auto mb-12">
            <h2 className="font-display font-bold text-3xl">Eight tools. One agent.</h2>
            <p className="mt-3 text-zinc-600 dark:text-zinc-400">
              A LangGraph ReAct loop picks the right tool for every sub-question, caches results
              in Redis, and streams checkpoints back over SSE as it works.
            </p>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {FEATURES.map(({ icon: Icon, title, desc }, i) => (
              <motion.div
                key={title}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.35, delay: (i % 4) * 0.05 }}
                className="rounded-2xl p-5 border transition
                  border-zinc-200 bg-white hover:border-zinc-300
                  dark:border-white/[0.06] dark:bg-white/[0.03] dark:hover:bg-white/[0.05]"
              >
                <Icon size={18} className="text-accent-violet dark:text-accent-cyan mb-3" />
                <div className="font-semibold text-sm">{title}</div>
                <div className="text-xs text-zinc-500 dark:text-zinc-400 mt-1.5 leading-relaxed">
                  {desc}
                </div>
              </motion.div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section className="max-w-4xl mx-auto px-6 pb-24">
          <div
            className="rounded-4xl p-10 text-center border
              border-zinc-200 bg-zinc-50
              dark:border-white/[0.08] dark:bg-white/[0.04]"
          >
            <h2 className="font-display font-bold text-2xl sm:text-3xl">
              Ask something worth researching.
            </h2>
            <p className="mt-3 text-zinc-600 dark:text-zinc-400">
              Free to try. No credit card required.
            </p>
            <Link
              to={user ? "/app" : "/register"}
              className="mt-6 inline-flex items-center gap-2 rounded-2xl px-6 py-3 font-semibold text-white bg-grad-vivid shadow-glow hover:scale-[1.02] active:scale-95 transition"
            >
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
