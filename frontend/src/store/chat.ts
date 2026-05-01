import { create } from "zustand";
import { api } from "@/lib/api";
import type { Conversation, Message } from "@/types";

interface ChatState {
  conversations: Conversation[];
  activeId: string | null;
  messages: Record<string, Message[]>;
  loading: boolean;

  loadConversations: () => Promise<void>;
  selectConversation: (id: string) => Promise<void>;
  createConversation: () => Promise<Conversation>;
  deleteConversation: (id: string) => Promise<void>;
  renameConversation: (id: string, title: string) => Promise<void>;
  setMessages: (convId: string, msgs: Message[]) => void;
  addMessage: (convId: string, msg: Message) => void;
  updateMessage: (convId: string, id: string, patch: Partial<Message>) => void;
  removeMessage: (convId: string, id: string) => void;
}

export const useChat = create<ChatState>((set, get) => ({
  conversations: [],
  activeId: null,
  messages: {},
  loading: false,

  loadConversations: async () => {
    set({ loading: true });
    try {
      const { data } = await api.get<Conversation[]>("/conversations");
      set({ conversations: data });
    } finally {
      set({ loading: false });
    }
  },

  selectConversation: async (id) => {
    set({ activeId: id });
    if (!get().messages[id]) {
      const { data } = await api.get<Message[]>(`/conversations/${id}/messages`);
      set((s) => ({ messages: { ...s.messages, [id]: data } }));
    }
  },

  createConversation: async () => {
    const { data } = await api.post<Conversation>("/conversations", {});
    set((s) => ({
      conversations: [data, ...s.conversations],
      activeId: data.id,
      messages: { ...s.messages, [data.id]: [] },
    }));
    return data;
  },

  deleteConversation: async (id) => {
    await api.delete(`/conversations/${id}`);
    set((s) => {
      const { [id]: _drop, ...rest } = s.messages;
      return {
        conversations: s.conversations.filter((c) => c.id !== id),
        messages: rest,
        activeId: s.activeId === id ? null : s.activeId,
      };
    });
  },

  renameConversation: async (id, title) => {
    await api.patch(`/conversations/${id}`, { title });
    set((s) => ({
      conversations: s.conversations.map((c) =>
        c.id === id ? { ...c, title } : c
      ),
    }));
  },

  setMessages: (convId, msgs) =>
    set((s) => ({ messages: { ...s.messages, [convId]: msgs } })),

  addMessage: (convId, msg) =>
    set((s) => ({
      messages: { ...s.messages, [convId]: [...(s.messages[convId] || []), msg] },
    })),

  updateMessage: (convId, id, patch) =>
    set((s) => ({
      messages: {
        ...s.messages,
        [convId]: (s.messages[convId] || []).map((m) =>
          m.id === id ? { ...m, ...patch } : m
        ),
      },
    })),

  removeMessage: (convId, id) =>
    set((s) => ({
      messages: {
        ...s.messages,
        [convId]: (s.messages[convId] || []).filter((m) => m.id !== id),
      },
    })),
}));
