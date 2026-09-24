import { lazy, Suspense, useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import {
  motion,
  useScroll,
  useSpring,
  useTransform,
  useMotionValue,
  useReducedMotion,
  useMotionValueEvent,
  type MotionValue,
} from "framer-motion";
import Lenis from "lenis";
import {
  X,
  Check,
  ArrowRight,
  Github,
} from "lucide-react";
import { useAuth } from "@/store/auth";
import ThemeToggle from "@/components/ThemeToggle";
import AgentTraceDemo from "@/components/AgentTraceDemo";
import "@/styles/landing.css";

const ResearchScene = lazy(() => import("@/components/landing/ResearchScene"));

const STAGES = [
  { key: "Ask", head: "Ask a hard question.", sub: "One box. No setup. Bring the question you can't Google in a minute." },
  { key: "Plan", head: "It plans the attack.", sub: "Your question splits into sub-questions, each with its own line of inquiry." },
  { key: "Search", head: "Fans out across the web.", sub: "Parallel searches pull in news, filings, markets and maps, live." },
  { key: "Read", head: "Reads what matters.", sub: "It opens the pages, keeps the relevant passages, drops the noise." },
  { key: "Cross-check", head: "Cross-checks every claim.", sub: "Sources that agree get linked. Conflicts get flagged, not smoothed over." },
  { key: "Answer", head: "Answers with receipts.", sub: "One clear answer, every claim tied to a source you can click." },
] as const;
const STEP = 1 / (STAGES.length - 1);

const GENERIC_ANSWER =
  "Yes, that funding round happened and the amount sounds about right based on what's publicly known.";
const LUMEN_ANSWER =
  "Confirmed — the $50M Series C closed Mar 4, filed with the SEC at $48.7M plus a $1.3M note.";
const GITHUB = "https://github.com/AnirudhGupta007/deep-research-platform";

/* ---------- small building blocks ---------- */

function Words({ text, className = "", delay = 0 }: { text: string; className?: string; delay?: number }) {
  return (
    <span className={className}>
      {text.split(" ").map((w, i) => (
        <span key={i} className="inline-block overflow-hidden align-bottom pb-[0.12em] -mb-[0.12em]">
          <motion.span
            className="inline-block"
            initial={{ y: "110%" }}
            whileInView={{ y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.8, delay: delay + i * 0.06, ease: [0.22, 1, 0.36, 1] }}
          >
            {w}&nbsp;
          </motion.span>
        </span>
      ))}
    </span>
  );
}

function Magnetic({ children }: { children: ReactNode }) {
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const sx = useSpring(x, { stiffness: 220, damping: 16 });
  const sy = useSpring(y, { stiffness: 220, damping: 16 });
  return (
    <motion.div
      style={{ x: sx, y: sy }}
      className="inline-block"
      onMouseMove={(e) => {
        const r = e.currentTarget.getBoundingClientRect();
        x.set((e.clientX - r.left - r.width / 2) * 0.25);
        y.set((e.clientY - r.top - r.height / 2) * 0.35);
      }}
      onMouseLeave={() => {
        x.set(0);
        y.set(0);
      }}
    >
      {children}
    </motion.div>
  );
}

const btnBase =
  "inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 text-sm font-medium transition-all duration-300";
const btnSolid = `${btnBase} bg-white text-zinc-950 hover:shadow-[0_0_40px_rgba(255,255,255,0.45)]`;
const btnGhost = `${btnBase} lumen-glass text-white hover:bg-white/10 hover:shadow-[0_0_30px_rgba(74,222,128,0.25)]`;

/** One pinned stage; hooks live here, not in a .map. */
function StageScene({ index, progress, children }: { index: number; progress: MotionValue<number>; children: ReactNode }) {
  const c = index * STEP;
  const h = STEP / 2;
  const first = index === 0;
  const last = index === STAGES.length - 1;
  const range = [c - h, c - h * 0.5, c + h * 0.5, c + h];
  const opacity = useTransform(progress, first ? [0, h * 0.5, h] : last ? [range[0], range[1], 1] : range, first ? [1, 1, 0] : last ? [0, 1, 1] : [0, 1, 1, 0]);
  const yr = first ? [0, h * 0.5, h] : last ? [range[0], range[1], 1] : range;
  const y = useTransform(progress, yr, first ? [0, 0, -40] : last ? [40, 0, 0] : [40, 0, 0, -40]);
  const pe = useTransform(opacity, (o) => (o > 0.15 ? "auto" : "none"));
  return (
    <motion.section
      style={{ opacity, y, pointerEvents: pe as unknown as "auto" | "none" }}
      className="absolute inset-0 flex flex-col items-center justify-center text-center px-6"
    >
      {children}
    </motion.section>
  );
}

function StageHeading({ i }: { i: number }) {
  const st = STAGES[i];
  return (
    <>
      <p className="text-[11px] tracking-[0.3em] uppercase text-emerald-300/80 mb-4">
        0{i + 1} / {st.key}
      </p>
      <h2 className="lumen-serif text-[13vw] sm:text-7xl lg:text-8xl leading-[0.98] max-w-4xl">{st.head}</h2>
      <p className="mt-6 text-zinc-300/80 text-base sm:text-lg max-w-md">{st.sub}</p>
    </>
  );
}

function RailItem({ label, i, active, onClick }: { label: string; i: number; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} aria-current={active} className="group flex sm:flex-row-reverse items-center gap-2 sm:gap-3 text-[10px] sm:text-[11px] tracking-[0.2em] uppercase">
      <span className={`transition-colors duration-300 ${active ? "text-white" : "text-zinc-500 group-hover:text-zinc-300"} ${active ? "" : "hidden sm:inline"}`}>{label}</span>
      <span className={`block rounded-full transition-all duration-300 ${active ? "w-2.5 h-2.5 bg-emerald-300 shadow-[0_0_14px_rgba(110,231,183,0.9)]" : "w-1.5 h-1.5 bg-white/30"}`} data-i={i} />
    </button>
  );
}

/* ---------- page ---------- */

export default function Landing() {
  const user = useAuth((s) => s.user);
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll();
  const bar = useSpring(scrollYProgress, { stiffness: 120, damping: 30 });

  // Lenis smooth scroll
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const lenis = new Lenis({ lerp: 0.1 });
    let raf = requestAnimationFrame(function tick(t) {
      lenis.raf(t);
      raf = requestAnimationFrame(tick);
    });
    return () => {
      cancelAnimationFrame(raf);
      lenis.destroy();
    };
  }, []);

  // Pinned stage: Ask -> Plan -> Search -> Read -> Cross-check -> Answer
  const stageRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress: sp } = useScroll({ target: stageRef, offset: ["start start", "end end"] });
  const hint = useTransform(sp, [0, 0.05], [1, 0]);
  const [active, setActive] = useState(0);
  useMotionValueEvent(sp, "change", (v) => {
    const n = Math.min(STAGES.length - 1, Math.max(0, Math.round(v / STEP)));
    setActive((a) => (a === n ? a : n));
  });
  const goStage = (i: number) => {
    const el = stageRef.current;
    if (!el) return;
    const top = el.getBoundingClientRect().top + window.scrollY;
    const span = el.offsetHeight - window.innerHeight;
    window.scrollTo({ top: top + span * i * STEP, behavior: reduce ? "auto" : "smooth" });
  };

  const primary = user ? "/app" : "/register";
  const primaryLabel = user ? "Open app" : "Get started";
  const ctaLabel = user ? "Open app" : "See it think";

  const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: reduce ? "auto" : "smooth" });

  return (
    <div className="lumen-landing lumen-stars relative text-zinc-100 min-h-screen">
      {/* fixed knowledge-graph scene (code-split). progress = pinned-stage scroll so the graph finishes with ANSWER */}
      <div className="lumen-backdrop" aria-hidden />
      <Suspense fallback={null}>
        <ResearchScene progress={sp} />
      </Suspense>

      {/* progress hairline */}
      <motion.div
        style={{ scaleX: bar }}
        className="fixed top-0 left-0 right-0 h-px origin-left bg-gradient-to-r from-transparent via-emerald-300 to-white z-50"
      />

      {/* floating pill nav */}
      <header className="fixed top-4 inset-x-0 z-40 flex justify-center px-3">
        <nav className="lumen-glass rounded-full pl-5 pr-2 py-2 flex items-center gap-3 sm:gap-6 max-w-full">
          <Link to="/" className="lumen-serif text-xl leading-none">Lumen</Link>
          <div className="hidden md:flex items-center gap-5 text-sm text-zinc-300">
            <button onClick={() => scrollTo("how")} className="hover:text-white transition">How it works</button>
            <button onClick={() => scrollTo("demo")} className="hover:text-white transition">Live demo</button>
            <a href={GITHUB} target="_blank" rel="noreferrer" className="hover:text-white transition">GitHub</a>
          </div>
          <ThemeToggle />
          {user ? (
            <Link to="/app" className="rounded-full bg-white text-zinc-950 text-sm font-medium px-4 py-1.5 hover:shadow-[0_0_24px_rgba(255,255,255,0.5)] transition">
              Open app
            </Link>
          ) : (
            <>
              <Link to="/login" className="hidden sm:inline text-sm text-zinc-300 hover:text-white px-2 transition">Log in</Link>
              <Link to="/register" className="rounded-full bg-white text-zinc-950 text-sm font-medium px-4 py-1.5 hover:shadow-[0_0_24px_rgba(255,255,255,0.5)] transition">
                Get started
              </Link>
            </>
          )}
        </nav>
      </header>

      <main className="relative z-10">
        {/* Pinned scenes, one per research stage */}
        <div ref={stageRef} className="relative h-[600vh]">
          <div id="how" className="absolute w-px h-px top-0" />
          <div className="sticky top-0 h-screen w-full overflow-hidden">
            {STAGES.map((st, i) => (
              <StageScene key={st.key} index={i} progress={sp}>
                {i === 0 && (
                  <div className="lumen-glass rounded-full px-3.5 py-1.5 text-xs text-zinc-300 inline-flex items-center gap-2 mb-6">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" /> Lumen · deep research agent
                  </div>
                )}
                <StageHeading i={i} />
                {i === 0 && (
                  <motion.div style={{ opacity: hint }} className="absolute bottom-8 text-[11px] tracking-[0.3em] uppercase text-zinc-500">
                    Scroll
                  </motion.div>
                )}
                {i === STAGES.length - 1 && (
                  <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
                    <Magnetic>
                      <Link to={primary} className={btnSolid}>{ctaLabel} <ArrowRight size={15} /></Link>
                    </Magnetic>
                    <Magnetic>
                      <button onClick={() => scrollTo("demo")} className={btnGhost}>Watch a live run ↓</button>
                    </Magnetic>
                  </div>
                )}
              </StageScene>
            ))}

            {/* stage rail */}
            <nav aria-label="Research stages" className="absolute z-20 flex gap-4 sm:gap-0 sm:flex-col sm:items-end sm:justify-center sm:gap-4 bottom-5 inset-x-0 justify-center sm:inset-x-auto sm:right-6 sm:top-0 sm:bottom-0">
              {STAGES.map((st, i) => (
                <RailItem key={st.key} label={st.key} i={i} active={active === i} onClick={() => goStage(i)} />
              ))}
            </nav>
          </div>
        </div>

        {/* 4 demo + comparison */}
        <section id="demo" className="relative px-5 sm:px-8 pt-24 pb-28 bg-gradient-to-b from-transparent via-[#05060b]/85 to-[#05060b]">
          <div className="max-w-3xl mx-auto text-center mb-12">
            <h2 className="lumen-serif text-4xl sm:text-6xl leading-tight">
              <Words text="Watch it think, step by step" />
            </h2>
          </div>
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.7 }}
          >
            <AgentTraceDemo />
          </motion.div>

          <div className="max-w-5xl mx-auto mt-28">
            <div className="text-center max-w-xl mx-auto mb-10">
              <h2 className="lumen-serif text-4xl sm:text-5xl">Same question. Different rigor.</h2>
              <p className="mt-3 text-zinc-400 text-sm sm:text-base">
                A generic chatbot guesses from memory. Lumen goes and checks.
              </p>
            </div>
            <div className="grid sm:grid-cols-2 gap-4">
              <motion.div initial={{ opacity: 0, x: -24 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ duration: 0.6 }} className="lumen-glass rounded-3xl p-6">
                <div className="flex items-center gap-2 mb-4 text-xs font-semibold uppercase tracking-wider text-zinc-400">
                  <X size={14} className="text-rose-400" /> Generic chatbot
                </div>
                <p className="text-sm text-zinc-500 italic leading-relaxed">{GENERIC_ANSWER}</p>
                <p className="mt-3 text-xs text-zinc-600">No sources. No way to verify.</p>
              </motion.div>
              <motion.div initial={{ opacity: 0, x: 24 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ duration: 0.6 }} className="rounded-3xl p-6 border border-emerald-400/30 bg-emerald-400/[0.06] backdrop-blur-md shadow-[0_0_60px_rgba(52,211,153,0.08)]">
                <div className="flex items-center gap-2 mb-4 text-xs font-semibold uppercase tracking-wider text-emerald-300">
                  <Check size={14} /> Lumen
                </div>
                <p className="text-sm text-zinc-200 leading-relaxed">{LUMEN_ANSWER}</p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {["techcrunch.com", "sec.gov"].map((s) => (
                    <span key={s} className="rounded-full border border-white/10 bg-white/5 px-2.5 py-0.5 text-xs text-zinc-400">{s}</span>
                  ))}
                </div>
              </motion.div>
            </div>
          </div>
        </section>

        {/* 5 footer horizon */}
        <footer className="relative overflow-hidden bg-[#05060b] rounded-t-[50%/60px] border-t border-white/10 shadow-[0_-30px_120px_rgba(52,211,153,0.10)] pt-20">
          <div className="max-w-6xl mx-auto px-6 grid grid-cols-2 md:grid-cols-4 gap-10">
            <div className="col-span-2 md:col-span-1">
              <h3 className="lumen-serif text-3xl leading-tight">Ask something worth researching.</h3>
              <div className="mt-6">
                <Magnetic>
                  <Link to={primary} className={btnSolid}>{primaryLabel} <ArrowRight size={15} /></Link>
                </Magnetic>
              </div>
            </div>
            <FooterCol title="Menu">
              <button onClick={() => scrollTo("how")}>How it works</button>
              <button onClick={() => scrollTo("demo")}>Live demo</button>
              {user ? <Link to="/app">Open app</Link> : <Link to="/login">Log in</Link>}
            </FooterCol>
            <FooterCol title="Socials">
              <a href={GITHUB} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5"><Github size={14} /> GitHub</a>
            </FooterCol>
            <FooterCol title="Resources">
              <a href={GITHUB} target="_blank" rel="noreferrer">Source code</a>
              <span className="text-zinc-600">LangGraph · Deep Agents · DeepSeek</span>
            </FooterCol>
          </div>
          <div className="mt-16 text-center select-none lumen-serif lumen-wordmark pb-4" aria-hidden>lumen</div>
          <div className="text-center text-xs text-zinc-600 pb-6 -mt-2">© {new Date().getFullYear()} Lumen — research, illuminated.</div>
        </footer>
      </main>
    </div>
  );
}

function FooterCol({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-[11px] tracking-[0.25em] uppercase text-zinc-500 mb-4">{title}</div>
      <div className="flex flex-col items-start gap-2.5 text-sm text-zinc-300 [&>*]:hover:text-white [&>*]:transition">{children}</div>
    </div>
  );
}
