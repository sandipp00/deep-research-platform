import { useEffect, useState, type KeyboardEvent } from "react";
import { useMatch, useNavigate } from "react-router-dom";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { Plus, MessageSquare, Trash2, Sparkles, LogOut, Check, X } from "lucide-react";
import { useChat } from "@/store/chat";
import { useAuth } from "@/store/auth";
import { conversationPath } from "@/lib/conversation";

export default function ConversationSidebar() {
  const nav = useNavigate();
  const routeId = useMatch("/app/c/:id")?.params.id;
  const conversations = useChat((s) => s.conversations);
  const activeId = useChat((s) => s.activeId);
  const load = useChat((s) => s.loadConversations);
  const create = useChat((s) => s.createConversation);
  const select = useChat((s) => s.selectConversation);
  const remove = useChat((s) => s.deleteConversation);
  const user = useAuth((s) => s.user);
  const logout = useAuth((s) => s.logout);
  const [confirmId, setConfirmId] = useState<string | null>(null);

  const reduce = useReducedMotion();
  useEffect(() => { load().catch(() => {}); }, [load]);
  useEffect(() => {
    if (!routeId) {
      useChat.setState({ activeId: null });
      return;
    }
    if (routeId === useChat.getState().activeId) return;
    select(routeId).catch(() => nav("/app", { replace: true }));
  }, [routeId, select, nav]);

  async function handleNew() {
    try {
      const c = await create();
      nav(conversationPath(c.id));
    } catch (e) {
      console.error("Failed to create conversation", e);
    }
  }

  async function handleDelete(id: string) {
    setConfirmId(null);
    try {
      await remove(id);
    } catch (e) {
      console.error("Failed to delete conversation", e);
      return;
    }
    if (routeId === id) nav("/app", { replace: true });
  }

  function onRowKey(e: KeyboardEvent<HTMLDivElement>, id: string) {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      nav(conversationPath(id));
    }
  }

  return (
    <aside className="w-72 shrink-0 h-full flex flex-col p-3 gap-3">
      <div className="glass-strong rounded-2xl p-3 flex items-center gap-2.5">
        <div className="w-9 h-9 rounded-xl bg-grad-vivid grid place-items-center shadow-glow">
          <Sparkles size={16} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-display font-bold gradient-text leading-none">Lumen</div>
          <div className="text-[10px] text-zinc-500 mt-0.5">research, illuminated.</div>
        </div>
      </div>

      <button onClick={handleNew} className="btn-primary w-full">
        <Plus size={16} />
        New chat
      </button>

      <nav aria-label="Conversations" className="glass-strong rounded-2xl p-2 flex-1 overflow-y-auto">
        {conversations.length === 0 ? (
          <div className="text-xs text-zinc-500 text-center py-8 px-3">
            No conversations yet. Start one above.
          </div>
        ) : (
          <ul className="space-y-1">
            <AnimatePresence initial>
            {conversations.map((c, i) => {
              const active = c.id === activeId;
              const confirming = confirmId === c.id;
              return (
                <motion.li
                  key={c.id}
                  layout={!reduce}
                  initial={{ opacity: 0, x: reduce ? 0 : -12 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: reduce ? 0 : -12 }}
                  transition={{ delay: Math.min(i, 10) * 0.035, type: "spring", stiffness: 380, damping: 30 }}
                  whileHover={reduce ? undefined : { x: 3 }}
                  className={`group relative rounded-xl flex items-center transition-colors border
                    ${active ? "border-white/[0.10]" : "hover:bg-white/[0.04] border-transparent"}`}
                >
                  {active && (
                    <motion.span
                      layoutId="conv-active"
                      transition={{ type: "spring", stiffness: 420, damping: 34 }}
                      className="pointer-events-none absolute inset-0 rounded-xl bg-white/[0.08]"
                    >
                      <span className="absolute left-0 top-2.5 bottom-2.5 w-[3px] rounded-full bg-accent-signal shadow-[0_0_10px_rgba(34,197,94,0.7)]" />
                    </motion.span>
                  )}
                  <div
                    role="link"
                    tabIndex={0}
                    aria-current={active ? "page" : undefined}
                    onClick={() => nav(conversationPath(c.id))}
                    onKeyDown={(e) => onRowKey(e, c.id)}
                    className="relative flex-1 min-w-0 cursor-pointer rounded-xl pl-3 pr-1 py-2.5 flex items-center gap-2
                               outline-none focus-visible:ring-2 focus-visible:ring-accent-signal/50"
                  >
                    <MessageSquare size={14} className={"shrink-0 " + (active ? "text-accent-cyan" : "text-zinc-500")} />
                    <span className="flex-1 text-sm truncate text-zinc-200">
                      {confirming ? "Delete this chat?" : c.title}
                    </span>
                  </div>
                  {confirming ? (
                    <div className="relative flex items-center gap-0.5 pr-2">
                      <button
                        type="button"
                        onClick={() => handleDelete(c.id)}
                        aria-label={`Confirm delete ${c.title}`}
                        className="p-1 rounded-md text-rose-400 hover:bg-rose-500/15 transition"
                        autoFocus
                      >
                        <Check size={14} />
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmId(null)}
                        aria-label="Cancel delete"
                        className="p-1 rounded-md text-zinc-400 hover:bg-white/[0.08] transition"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => setConfirmId(c.id)}
                      aria-label={`Delete conversation ${c.title}`}
                      className="relative mr-2 p-1 rounded-md opacity-0 group-hover:opacity-100 focus-visible:opacity-100
                                 transition text-zinc-500 hover:text-rose-400"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </motion.li>
              );
            })}
            </AnimatePresence>
          </ul>
        )}
      </nav>

      <div className="glass-strong rounded-2xl p-3 flex items-center gap-2.5">
        <div className="w-9 h-9 rounded-xl bg-grad-vivid grid place-items-center font-display font-semibold text-sm shadow-glow text-white">
          {user?.name?.[0]?.toUpperCase() ?? "?"}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">{user?.name}</div>
          <div className="text-[10px] text-zinc-500 truncate">{user?.email}</div>
        </div>
        <button
          type="button"
          onClick={() => { logout(); nav("/login"); }}
          aria-label="Log out"
          title="Log out"
          className="p-2 rounded-xl text-zinc-400 hover:text-white hover:bg-white/[0.06] transition"
        >
          <LogOut size={14} />
        </button>
      </div>
    </aside>
  );
}
