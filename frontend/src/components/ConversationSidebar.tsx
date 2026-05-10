import { useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import { Plus, MessageSquare, Trash2, Sparkles, LogOut } from "lucide-react";
import { useChat } from "@/store/chat";
import { useAuth } from "@/store/auth";

export default function ConversationSidebar() {
  const nav = useNavigate();
  const { id: routeId } = useParams();
  const conversations = useChat((s) => s.conversations);
  const activeId = useChat((s) => s.activeId);
  const load = useChat((s) => s.loadConversations);
  const create = useChat((s) => s.createConversation);
  const select = useChat((s) => s.selectConversation);
  const remove = useChat((s) => s.deleteConversation);
  const user = useAuth((s) => s.user);
  const logout = useAuth((s) => s.logout);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (routeId && routeId !== activeId) select(routeId);
  }, [routeId, activeId, select]);

  async function handleNew() {
    const c = await create();
    nav(`/c/${c.id}`);
  }

  async function handleDelete(e: React.MouseEvent, id: string) {
    e.stopPropagation();
    if (!confirm("Delete this conversation?")) return;
    await remove(id);
    if (activeId === id) nav("/");
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

      <div className="glass-strong rounded-2xl p-2 flex-1 overflow-y-auto">
        {conversations.length === 0 ? (
          <div className="text-xs text-zinc-500 text-center py-8 px-3">
            No conversations yet. Start one above.
          </div>
        ) : (
          <ul className="space-y-1">
            {conversations.map((c) => {
              const active = c.id === activeId;
              return (
                <motion.li key={c.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                  <button
                    onClick={() => nav(`/c/${c.id}`)}
                    className={`group w-full text-left rounded-xl px-3 py-2.5 flex items-center gap-2 transition
                      ${active ? "bg-white/[0.08] border border-white/[0.10]" : "hover:bg-white/[0.04] border border-transparent"}`}
                  >
                    <MessageSquare size={14} className={active ? "text-accent-cyan" : "text-zinc-500"} />
                    <span className="flex-1 text-sm truncate text-zinc-200">{c.title}</span>
                    <button
                      onClick={(e) => handleDelete(e, c.id)}
                      className="opacity-0 group-hover:opacity-100 transition text-zinc-500 hover:text-rose-400"
                      aria-label="Delete"
                    >
                      <Trash2 size={14} />
                    </button>
                  </button>
                </motion.li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="glass-strong rounded-2xl p-3 flex items-center gap-2.5">
        <div className="w-9 h-9 rounded-xl bg-grad-vivid grid place-items-center font-display font-semibold text-sm shadow-glow text-white">
          {user?.name?.[0]?.toUpperCase() ?? "?"}
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">{user?.name}</div>
          <div className="text-[10px] text-zinc-500 truncate">{user?.email}</div>
        </div>
        <button onClick={() => { logout(); nav("/login"); }}
                className="p-2 rounded-xl text-zinc-400 hover:text-white hover:bg-white/[0.06] transition">
          <LogOut size={14} />
        </button>
      </div>
    </aside>
  );
}
