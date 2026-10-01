import { create } from "zustand";
import { api } from "@/lib/api";
import type { User } from "@/types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
}

function readStoredUser(): User | null {
  try {
    const raw = localStorage.getItem("auth_user");
    return raw && localStorage.getItem("auth_token") ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

export const useAuth = create<AuthState>((set) => ({
  user: readStoredUser(),
  loading: false,

  login: async (email, password) => {
    set({ loading: true });
    try {
      const { data } = await api.post("/auth/login", { email, password });
      localStorage.setItem("auth_token", data.token);
      const u = { id: data.id, email: data.email, name: data.name };
      localStorage.setItem("auth_user", JSON.stringify(u));
      set({ user: u });
    } finally {
      set({ loading: false });
    }
  },

  register: async (email, password, name) => {
    set({ loading: true });
    try {
      const { data } = await api.post("/auth/register", { email, password, name });
      localStorage.setItem("auth_token", data.token);
      const u = { id: data.id, email: data.email, name: data.name };
      localStorage.setItem("auth_user", JSON.stringify(u));
      set({ user: u });
    } finally {
      set({ loading: false });
    }
  },

  logout: () => {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_user");
    set({ user: null });
  },
}));
