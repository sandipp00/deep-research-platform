import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Sparkles, TrendingUp, Newspaper, MapPin, Bitcoin, DollarSign, BookOpen } from "lucide-react";
import { useAuth } from "@/store/auth";
import { useChat } from "@/store/chat";
import { postSse } from "@/lib/sse";
import type { Block, Checkpoint, FollowUp, Message } from "@/types";
import MessageBubble from "./MessageBubble";
import ChatInput from "./ChatInput";

const SUGGESTIONS: { label: string; icon: JSX.Element }[] = [
  { label: "EV charging stations in Lucknow", icon: <MapPin size={14} className="text-accent-cyan" /> },
  { label: "Latest RBI policy update",        icon: <Newspaper size={14} className="text-accent-pink" /> },
  { label: "Bitcoin price in INR",            icon: <Bitcoin size={14} className="text-amber-300" /> },
  { label: "Top IT stocks on NSE today",      icon: <TrendingUp size={14} className="text-emerald-300" /> },
  { label: "Hospitals near Koramangala Bangalore", icon: <MapPin size={14} className="text-accent-violet" /> },
  { label: "1000 USD to INR",                 icon: <DollarSign size={14} className="text-emerald-300" /> },
];

function timeGreeting(): string {
  const h = new Date().getHours();
  if (h < 5)  return "Burning the midnight oil";
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  if (h < 21) return "Good evening";
  return "Working late";
}

export default function ChatPanel() {
  const nav = useNavigate();
  const activeId = useChat((s) => s.activeId);
  const allMsgs = useChat((s) => s.messages);
  const addMessage = useChat((s) => s.addMessage);
  const updateMessage = useChat((s) => s.updateMessage);
  const createConversation = useChat((s) => s.createConversation);
  const renameConversation = useChat((s) => s.renameConversation);
  const select = useChat((s) => s.selectConversation);

  const messages = useMemo(() => (activeId ? allMsgs[activeId] || [] : []), [activeId, allMsgs]);

  const [streaming, setStreaming] = useState(false);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [pendingAssistantId, setPendingAssistantId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);

  // Track whether the user has scrolled up — if so, don't yank them back.
  function onScroll() {
    const el = scrollRef.current;
    if (!el) return;
    const distFromBottom = el.scrollHeight - el.clientHeight - el.scrollTop;
    stickToBottomRef.current = distFromBottom < 80;
  }

  useEffect(() => {
    if (!stickToBottomRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    // 'auto' (instant) during stream so rapid checkpoints don't jitter; 'smooth' otherwise.
    el.scrollTo({ top: el.scrollHeight, behavior: streaming ? "auto" : "smooth" });
  }, [messages.length, checkpoints.length, streaming]);

  async function send(text: string) {
    let convId = activeId;
    if (!convId) {
      const c = await createConversation();
      convId = c.id;
      nav(`/c/${convId}`);
      await select(convId);
    }
    if (!convId) return;

    // Optimistic user + assistant placeholder
    const tempUser: Message = {
      id: `tmp-user-${Date.now()}`,
      role: "user",
      content: text,
      createdAt: new Date().toISOString(),
    };
    const tempAssistant: Message = {
      id: `tmp-asst-${Date.now()}`,
      role: "assistant",
      content: "",
      blocks: [],
      sources: [],
      followUps: [],
      createdAt: new Date().toISOString(),
    };
    addMessage(convId, tempUser);
    addMessage(convId, tempAssistant);
    setPendingAssistantId(tempAssistant.id);
    setCheckpoints([]);
    setStreaming(true);
    stickToBottomRef.current = true;  // a new turn — follow it down

    if (messages.length === 0) {
      const newTitle = text.length > 60 ? text.slice(0, 57) + "..." : text;
      renameConversation(convId, newTitle).catch(() => {});
    }

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    let collectedBlocks: Block[] = [];
    let collectedSources: string[] = [];
    let collectedFollowUps: FollowUp[] = [];
    let collectedText = "";

    try {
      await postSse(`/conversations/${convId}/query`, { query: text }, {
        signal: ctrl.signal,
        onEvent: (msg) => {
          if (!msg.event) return;
          let data: any = {};
          try { data = JSON.parse(msg.data); } catch {}

          switch (msg.event) {
            case "user_message":
              if (data.id) {
                updateMessage(convId!, tempUser.id, { id: data.id });
              }
              break;
            case "checkpoint":
              setCheckpoints((cs) => [
                ...cs,
                { status: data.status, content: data.content, tool: data.tool, ts: Date.now() },
              ]);
              break;
            case "blocks": {
              const payload = data.data || {};
              collectedBlocks = payload.blocks || [];
              collectedSources = payload.sources || [];
              collectedFollowUps = payload.follow_ups || [];
              const md = collectedBlocks.find((b) => b.template_id === "markdown") as any;
              collectedText = md?.data?.content || "";
              updateMessage(convId!, tempAssistant.id, {
                content: collectedText,
                blocks: collectedBlocks,
                sources: collectedSources,
                followUps: collectedFollowUps,
              });
              break;
            }
            case "clarification":
              collectedText = data.content || "";
              updateMessage(convId!, tempAssistant.id, {
                content: collectedText,
                blocks: [{ template_id: "markdown", data: { content: collectedText } }],
              });
              break;
            case "error":
              collectedText = data.content || "Something went wrong.";
              updateMessage(convId!, tempAssistant.id, {
                content: collectedText,
                blocks: [{ template_id: "markdown", data: { content: `⚠️ ${collectedText}` } }],
              });
              break;
            case "persisted":
              if (data.messageId) {
                updateMessage(convId!, tempAssistant.id, { id: data.messageId });
              }
              break;
          }
        },
        onError: (e) => {
          console.error("SSE error", e);
          updateMessage(convId!, tempAssistant.id, {
            content: "Connection lost. Please retry.",
            blocks: [{ template_id: "markdown", data: { content: "⚠️ Connection lost. Please retry." } }],
          });
        },
      });
    } catch (e) {
      // already handled in onError
    } finally {
      setStreaming(false);
      setPendingAssistantId(null);
      setCheckpoints([]);
      abortRef.current = null;
    }
  }

  function stop() {
    abortRef.current?.abort();
    setStreaming(false);
    if (pendingAssistantId && activeId) {
      updateMessage(activeId, pendingAssistantId, {
        content: "Stopped.",
        blocks: [{ template_id: "markdown", data: { content: "_Stopped by user._" } }],
      });
    }
    setPendingAssistantId(null);
  }

  function handleFollowUp(f: FollowUp) {
    send(f.query);
  }

  return (
    <main className="flex-1 h-full flex flex-col p-3 pl-0 min-w-0">
      <div className="glass-strong rounded-3xl flex-1 flex flex-col overflow-hidden">
        <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto overscroll-contain px-6 py-6 space-y-6">
          {messages.length === 0 ? (
            <Welcome onPick={(s) => send(s)} />
          ) : (
            messages.map((m) => (
              <MessageBubble
                key={m.id}
                message={m}
                streaming={streaming && m.id === pendingAssistantId}
                checkpoints={m.id === pendingAssistantId ? checkpoints : undefined}
                onFollowUp={handleFollowUp}
              />
            ))
          )}
        </div>

        <div className="px-4 pb-4 pt-2 border-t border-white/[0.06]">
          <ChatInput onSend={send} onStop={stop} busy={streaming} />
        </div>
      </div>
    </main>
  );

  function Welcome({ onPick }: { onPick: (s: string) => void }) {
    const user = useAuth((s) => s.user);
    const firstName = user?.name?.split(" ")[0] ?? "";
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="relative h-full grid place-items-center text-center px-6 overflow-hidden"
      >
        <div className="pointer-events-none absolute inset-0 -z-0">
          <div className="absolute -top-32 -left-24 w-[28rem] h-[28rem] rounded-full
                          bg-accent-violet/25 blur-[100px] animate-[float_12s_ease-in-out_infinite]" />
          <div className="absolute -top-10 right-0 w-[26rem] h-[26rem] rounded-full
                          bg-accent-pink/20 blur-[100px] animate-[float_14s_ease-in-out_infinite_reverse]" />
          <div className="absolute bottom-0 left-1/3 w-[24rem] h-[24rem] rounded-full
                          bg-accent-cyan/20 blur-[110px] animate-[float_18s_ease-in-out_infinite]" />
        </div>

        <div className="relative max-w-xl">
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="inline-flex items-center gap-2 chip mb-6"
          >
            <Sparkles size={12} className="text-accent-pink" />
            Powered by Deep Agents
          </motion.div>
          <h1 className="text-4xl sm:text-5xl font-display font-bold leading-tight">
            {timeGreeting()}{firstName ? `, ${firstName}` : ""} —<br />
            what can I <span className="gradient-text">research</span> for you?
          </h1>
          <p className="text-zinc-400 mt-3">
            Stocks · forex · crypto · news · nearby places · regulations · general research.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 mt-8 text-left">
            {SUGGESTIONS.map((s, i) => (
              <motion.button
                key={s.label}
                onClick={() => onPick(s.label)}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 + i * 0.04 }}
                whileHover={{ y: -2 }}
                className="glass rounded-2xl px-4 py-3 text-sm text-zinc-200
                           hover:border-accent-violet/40 hover:bg-white/[0.07] transition
                           text-left flex items-center gap-2.5"
              >
                <span className="shrink-0 w-7 h-7 rounded-xl grid place-items-center
                                 bg-white/[0.05] border border-white/[0.06]">
                  {s.icon}
                </span>
                <span className="truncate">{s.label}</span>
              </motion.button>
            ))}
          </div>
        </div>
      </motion.div>
    );
  }
}
