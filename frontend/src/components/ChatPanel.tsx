import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import { useChat } from "@/store/chat";
import { postSse } from "@/lib/sse";
import type { Block, Checkpoint, FollowUp, Message } from "@/types";
import MessageBubble from "./MessageBubble";
import ChatInput from "./ChatInput";

const SUGGESTIONS = [
  "EV charging stations in Lucknow",
  "Latest RBI policy update",
  "Bitcoin price in INR",
  "Top IT stocks on NSE today",
  "Hospitals near Koramangala Bangalore",
  "1000 USD to INR",
];

export default function ChatPanel() {
  const nav = useNavigate();
  const { id: routeId } = useParams();
  const activeId = useChat((s) => s.activeId);
  const allMsgs = useChat((s) => s.messages);
  const addMessage = useChat((s) => s.addMessage);
  const updateMessage = useChat((s) => s.updateMessage);
  const removeMessage = useChat((s) => s.removeMessage);
  const createConversation = useChat((s) => s.createConversation);
  const renameConversation = useChat((s) => s.renameConversation);
  const select = useChat((s) => s.selectConversation);

  const messages = useMemo(() => (activeId ? allMsgs[activeId] || [] : []), [activeId, allMsgs]);

  const [streaming, setStreaming] = useState(false);
  const [checkpoints, setCheckpoints] = useState<Checkpoint[]>([]);
  const [pendingAssistantId, setPendingAssistantId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
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
              setCheckpoints((cs) => [...cs, { status: data.status, content: data.content, tool: data.tool }]);
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
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
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
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="h-full grid place-items-center text-center px-6"
      >
        <div className="max-w-xl">
          <div className="inline-flex items-center gap-2 chip mb-6">
            <Sparkles size={12} className="text-accent-pink" />
            Powered by Deep Agents
          </div>
          <h1 className="text-4xl sm:text-5xl font-display font-bold leading-tight">
            What can I <span className="gradient-text">research</span> for you?
          </h1>
          <p className="text-zinc-400 mt-3">
            Stocks · forex · crypto · news · nearby places · regulations · general research.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 mt-8 text-left">
            {SUGGESTIONS.map((s) => (
              <button key={s} onClick={() => onPick(s)}
                className="glass rounded-2xl px-4 py-3 text-sm text-zinc-200 hover:border-accent-violet/40 hover:bg-white/[0.06] transition text-left">
                {s}
              </button>
            ))}
          </div>
        </div>
      </motion.div>
    );
  }
}
