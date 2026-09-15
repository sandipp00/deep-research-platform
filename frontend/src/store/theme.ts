import { create } from "zustand";

export type Theme = "dark" | "light";

function apply(theme: Theme) {
  const root = document.documentElement;
  root.classList.toggle("dark", theme === "dark");
  root.classList.toggle("light", theme === "light");
}

interface ThemeState {
  theme: Theme;
  init: () => void;
  toggle: () => void;
  set: (t: Theme) => void;
}

export const useTheme = create<ThemeState>((set, get) => ({
  theme: "dark",

  init: () => {
    let stored: Theme | null = null;
    try {
      stored = localStorage.getItem("lumen_theme") as Theme | null;
    } catch {}
    const theme = stored === "light" || stored === "dark" ? stored : "dark";
    apply(theme);
    set({ theme });
  },

  set: (theme) => {
    apply(theme);
    try { localStorage.setItem("lumen_theme", theme); } catch {}
    set({ theme });
  },

  toggle: () => {
    const next: Theme = get().theme === "dark" ? "light" : "dark";
    apply(next);
    try { localStorage.setItem("lumen_theme", next); } catch {}
    set({ theme: next });
  },
}));
