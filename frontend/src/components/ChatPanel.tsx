import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import { Sparkles, TrendingUp, Newspaper, MapPin, Bitcoin, DollarSign } from "lucide-react";
import { useAuth } from "@/store/auth";
import { useChat } from "@/store/chat";
import { postSse } from "@/lib/sse";
import { ApiError } from "@/lib/errors";
import { conversationPath, titleFromQuery } from "@/lib/conversation";
import type { Block, Checkpoint, FollowUp, Message } from "@/types";
import MessageBubble from "./MessageBubble";
import ChatInput from "./ChatInput";

const SUGGESTIONS: { label: string; icon: JSX.Element }[] = [
  { label: "EV charging stations in Lucknow", icon: <MapPin size={14} className="text-zinc-400" /> },
  { label: "Latest RBI policy update",        icon: <Newspaper size={14} className="text-zinc-400" /> },
  { label: "Bitcoin price in INR",            icon: <Bitcoin size={14} className="text-zinc-400" /> },
  { label: "Top IT stocks on NSE today",      icon: <TrendingUp size={14} className="text-zinc-400" /> },
  { label: "Hospitals near Koramangala Bangalore", icon: <MapPin size={14} className="text-zinc-400" /> },
  { label: "1000 USD to INR",                 icon: <DollarSign size={14} className="text-zinc-400" /> },
];

function timeGreeting(): string {
  const h = new Date().getHours();
  if (h < 5)  return "Burning the midnight oil";
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  if (h < 21) return "Good evening";
  return "Working late";
}

let keySeq = 0;
function newClientKey(prefix: string): string {
  keySeq += 1;
  return `tmp-${prefix}-${Date.now()}-${keySeq}`;
}

function markdownBlock(content: string): Block[] {
  return [{ template_id: "markdown", data: { content } }];
}

interface ActiveStream {
  convId: string;
  assistantKey: string;
  ctrl: AbortController;
  stopped: boolean;
}

export default function ChatPanel() {
  const nav = useNavigate();
  const activeId = useChat((s) => s.activeId);
  const allMsgs = useChat((s) => s.messages);

  const messages = useMemo(() => (activeId ? allMsgs[activeId] || [] : []), [activeId, allMsgs]);

  const [streaming, setStreaming] = useState(false);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const streamRef = useRef<ActiveStream | null>(null);
  const reduce = useReducedMotion();
  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);

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
    el.scrollTo({ top: el.scrollHeight, behavior: streaming || reduce ? "auto" : "smooth" });
  }, [messages.length, checkpoints.length, streaming, reduce]);

  async function send(text: string) {
    if (streamRef.current) return;
    const store = useChat.getState();

    let convId = store.activeId;
    if (!convId) {
      try {
        const c = await store.createConversation();
        convId = c.id;
      } catch (e) {
        console.error("Failed to create conversation", e);
        return;
      }
      nav(conversationPath(convId), { replace: true });
    }

    const isFirstMessage = (useChat.getState().messages[convId]?.length ?? 0) === 0;

    const userKey = newClientKey("user");
    const assistantKey = newClientKey("asst");
    const now = new Date().toISOString();
    const tempUser: Message = { id: userKey, clientKey: userKey, role: "user", content: text, createdAt: now };
    const tempAssistant: Message = {
      id: assistantKey,
      clientKey: assistantKey,
      role: "assistant",
      content: "",
      blocks: [],
      sources: [],
      followUps: [],
      createdAt: now,
    };

    const { addMessage, updateMessage, renameConversation } = useChat.getState();
    addMessage(convId, tempUser);
    addMessage(convId, tempAssistant);

    const ctrl = new AbortController();
    const stream: ActiveStream = { convId, assistantKey, ctrl, stopped: false };
    streamRef.current = stream;
    setPendingKey(assistantKey);
    setCheckpoints([]);
    setStreaming(true);
    stickToBottomRef.current = true;

    if (isFirstMessage) {
      renameConversation(convId, titleFromQuery(text)).catch(() => {});
    }

    const target = convId;
    const patchAssistant = (patch: Partial<Message>) => {
      if (stream.stopped) return;
      useChat.getState().updateMessage(target, assistantKey, patch);
    };

    try {
      await postSse(`/conversations/${target}/query`, { query: text }, {
        signal: ctrl.signal,
        onEvent: (msg) => {
          if (!msg.event || stream.stopped) return;
          let data: any = {};
          try { data = JSON.parse(msg.data); } catch { data = {}; }

          switch (msg.event) {
            case "user_message":
              if (data.id) updateMessage(target, userKey, { id: data.id });
              break;
            case "checkpoint":
              setCheckpoints((cs) => [
                ...cs,
                { status: data.status, content: data.content, tool: data.tool, ts: Date.now() },
              ]);
              break;
            case "blocks": {
              const payload = data.data || {};
              const blocks: Block[] = payload.blocks || [];
              const md = blocks.find((b) => b.template_id === "markdown") as { data?: { content?: string } } | undefined;
              patchAssistant({
                content: md?.data?.content || "",
                blocks,
                sources: payload.sources || [],
                followUps: payload.follow_ups || [],
              });
              break;
            }
            case "clarification": {
              const content = data.content || "";
              patchAssistant({ content, blocks: markdownBlock(content) });
              break;
            }
            case "error": {
              const content = data.content || "Something went wrong.";
              patchAssistant({ content, blocks: markdownBlock(`⚠️ ${content}`) });
              break;
            }
            case "persisted":
              if (data.messageId) updateMessage(target, assistantKey, { id: data.messageId });
              break;
          }
        },
        onError: (e) => {
          console.error("SSE error", e);
          const content = e instanceof ApiError ? e.message : "Connection lost. Please retry.";
          patchAssistant({ content, blocks: markdownBlock(`⚠️ ${content}`) });
        },
      });
    } catch {
      return;
    } finally {
      if (streamRef.current === stream) {
        streamRef.current = null;
        setStreaming(false);
        setPendingKey(null);
        setCheckpoints([]);
      }
    }
  }

  function stop() {
    const stream = streamRef.current;
    if (!stream) return;
    stream.stopped = true;
    stream.ctrl.abort();
    useChat.getState().updateMessage(stream.convId, stream.assistantKey, {
      content: "Stopped.",
      blocks: markdownBlock("_Stopped by user._"),
    });
    streamRef.current = null;
    setStreaming(false);
    setPendingKey(null);
    setCheckpoints([]);
  }

  function handleFollowUp(f: FollowUp) {
    send(f.query);
  }

  return (
    <main className="flex-1 h-full flex flex-col p-3 pl-0 min-w-0">
      <div className="glass-strong rounded-3xl flex-1 flex flex-col overflow-hidden">
        <div ref={scrollRef} onScroll={onScroll} className="flex-1 overflow-y-auto overscroll-contain px-6 py-6 space-y-6">
          {messages.length === 0 ? (
            <Welcome onPick={send} />
          ) : (
            messages.map((m) => {
              const key = m.clientKey ?? m.id;
              const pending = pendingKey !== null && key === pendingKey;
              return (
                <MessageBubble
                  key={key}
                  message={m}
                  streaming={streaming && pending}
                  checkpoints={pending ? checkpoints : undefined}
                  onFollowUp={handleFollowUp}
                />
              );
            })
          )}
        </div>

        <div className="px-4 pb-4 pt-2 border-t border-white/[0.06]">
          <ChatInput onSend={send} onStop={stop} busy={streaming} />
        </div>
      </div>
    </main>
  );
}

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
                        bg-accent-signal/12 blur-[100px] animate-[float_12s_ease-in-out_infinite]" />
        <div className="absolute bottom-0 right-1/4 w-[24rem] h-[24rem] rounded-full
                        bg-accent-signal/8 blur-[110px] animate-[float_18s_ease-in-out_infinite_reverse]" />
      </div>

      <div className="relative max-w-xl">
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
          className="inline-flex items-center gap-2 chip mb-6"
        >
          <Sparkles size={12} className="text-accent-signal" />
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
                         hover:border-accent-signal/40 hover:bg-white/[0.07] transition
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
